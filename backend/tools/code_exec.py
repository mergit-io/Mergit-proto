import asyncio
import sys

from tracing import trace


@trace("code_exec")
async def code_exec(args: dict) -> dict:
    code = args["code"]
    timeout = args.get("timeout", 30)

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        exit_code = proc.returncode
        return {
            "stdout": stdout.decode()[:8192],
            "stderr": stderr.decode()[:2048],
            "exit_code": exit_code,
            "ok": exit_code == 0,
        }
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return {"stdout": "", "stderr": f"Execution timed out after {timeout}s", "exit_code": -1, "ok": False}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "exit_code": -1, "ok": False}


SCHEMA = {
    "description": "Execute Python code in a subprocess and return stdout/stderr.",
    "type": "object",
    "properties": {
        "code": {"type": "string", "description": "Python code to execute"},
        "timeout": {"type": "integer", "default": 30, "description": "Timeout in seconds"},
    },
    "required": ["code"],
}
