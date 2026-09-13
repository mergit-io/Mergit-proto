"""Run model-authored Python, without handing it the keys to the building.

This tool executes code a language model wrote, in a subprocess of the API server. Until
it runs out of process entirely (a sandbox API — the Phase 6 item), the job here is to
make the blast radius as small as a subprocess can be:

  * **A scrubbed environment.** The original passed no `env=`, so the child inherited the
    parent's — `GITHUB_TOKEN`, every provider key, `CHAIN_PRIVATE_KEY`, and the KEK that
    unwraps stored OAuth tokens. `print(os.environ)` then flowed to stdout, into the tool
    result, into `tool_calls`, over SSE, and back into the model's own context. That is
    the whole credential set, exfiltrated by four words of Python.
  * **`-I` (isolated mode).** Ignores `PYTHON*` env vars and drops the script directory
    and the user site-packages from `sys.path`, so the child cannot be steered by a file
    written earlier via `file_ops`.
  * **A scratch cwd.** The child starts in an empty temp directory, not in `backend/`
    beside `mergit.db`.
  * **Resource limits and a process group.** CPU, address space, file size and process
    count are capped, and the whole group is killed on timeout — the original killed only
    the direct child, so anything it spawned survived the timeout and kept running.

None of this is a security boundary. A determined escape from a same-user subprocess is
not hard, which is exactly why `DEMO_SAFE_MODE` exists: on a public deployment the tool is
not registered at all. Do not describe this file as a sandbox.
"""
import asyncio
import os
import shutil
import signal
import sys
import tempfile
import textwrap

#: Bytes of stdout/stderr returned to the model. Beyond this the tail is dropped, because
#: the result is about to become part of a prompt.
_STDOUT_LIMIT = 8192
_STDERR_LIMIT = 2048

#: Names that may cross into the child. Everything else — every key, token and secret —
#: is left behind. This is an allowlist on purpose: a denylist grows a hole every time
#: someone adds a credential to `config.Settings` and forgets this file.
_ENV_ALLOWLIST = ("PATH", "LANG", "LC_ALL", "TZ", "HOME", "TMPDIR", "SYSTEMROOT")

#: Applied inside the child before the model's code runs. `resource` is POSIX-only, so the
#: import is guarded rather than assumed — Windows dev machines still get isolation and a
#: timeout, just not rlimits.
_PREAMBLE = textwrap.dedent(
    """
    import sys
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (25, 25))
        resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))       # 1 GiB
        resource.setrlimit(resource.RLIMIT_FSIZE, (32 << 20, 32 << 20))  # 32 MiB
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except Exception:
        pass
    __mergit_code = sys.stdin.read()
    exec(compile(__mergit_code, "<agent_code>", "exec"), {"__name__": "__main__"})
    """
).strip()


def _child_env() -> dict:
    env = {k: os.environ[k] for k in _ENV_ALLOWLIST if k in os.environ}
    # Keep the child from writing .pyc files into a directory it should not own, and make
    # its output arrive unbuffered so a timeout still yields whatever it managed to print.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    return env


async def code_exec(args: dict) -> dict:
    code = args["code"]
    timeout = min(int(args.get("timeout", 30) or 30), 60)

    workdir = tempfile.mkdtemp(prefix="mergit-exec-")
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-I", "-c", _PREAMBLE,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir,
            env=_child_env(),
            # A new session, so `killpg` below reaches anything the code spawned.
            # Deliberately NOT `preexec_fn`: it is documented as unsafe in a process with
            # threads, and LiteLLM runs threads. The rlimits go in the child preamble.
            start_new_session=True,
        )
        # The code is piped in rather than passed as an argv string. `-c` with a long
        # program can exceed the argument limit, and the source would otherwise show up
        # in `ps` for every process on the box.
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=code.encode()), timeout=timeout
        )
        exit_code = proc.returncode
        return {
            "stdout": stdout.decode(errors="replace")[:_STDOUT_LIMIT],
            "stderr": stderr.decode(errors="replace")[:_STDERR_LIMIT],
            "exit_code": exit_code,
            "ok": exit_code == 0,
        }
    except asyncio.TimeoutError:
        await _terminate(proc)
        return {"stdout": "", "stderr": f"Execution timed out after {timeout}s",
                "exit_code": -1, "ok": False}
    except Exception as e:
        await _terminate(proc)
        return {"stdout": "", "stderr": str(e), "exit_code": -1, "ok": False}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


async def _terminate(proc) -> None:
    """Kill the child, everything it started, and then reap it.

    Two things here, both necessary:

    * `proc.kill()` alone leaves grandchildren running — code that spawns a background
      process and then hangs would survive its own timeout and keep consuming the box.
      Killing the process *group* is what actually stops it.
    * The `await proc.wait()` is not optional tidiness. Without it the transport is
      finalised later, by the garbage collector, on an event loop that has since been
      closed — which raises `RuntimeError: Event loop is closed` from a destructor, at a
      point in the program with no relationship to the code that caused it.
    """
    if proc is None or proc.returncode is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            return
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except Exception:
        pass


SCHEMA = {
    "description": (
        "Execute Python code in an isolated subprocess and return stdout/stderr. "
        "The process has no network credentials, starts in an empty temporary directory, "
        "and is CPU- and memory-limited. Write self-contained code and print its results."
    ),
    "type": "object",
    "properties": {
        "code": {"type": "string", "description": "Python code to execute"},
        "timeout": {"type": "integer", "default": 30,
                    "description": "Timeout in seconds (max 60)"},
    },
    "required": ["code"],
}
