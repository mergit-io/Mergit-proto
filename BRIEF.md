# Mergit — system and reliability brief

**One sentence in. Four apps touched. Every claim checked against the service that would know.**

> "Close the loop on the bug reported in the #eng-bugs Slack thread."

Mergit reads the thread, writes the fix, opens a real pull request, files and moves a Linear
ticket, writes a Notion incident note, and replies in the thread that asked — in under
three minutes, with no human in the loop, against a codebase of about a thousand lines it
has never seen.

## System

A planning model turns the sentence into a task graph: every node assigned to an agent,
with inputs and dependencies resolved. Five specialist agents (`researcher`, `writer`,
`coder`, `integrator`, and `operator` for the experimental interleaved executor) share **42
registered tools** — 21 GitHub, 5 Slack, 6 Linear, 4 Notion, plus code execution, web
search and HTTP. Independent nodes run in parallel, five at a time.

Credentials resolve through one path for every service: the goal owner's stored connection,
then an explicit caller, then a deployment token. Tokens are AES-GCM sealed per user and
read only inside `credentials/` — a test asserts that the broker is the sole importer of
the unseal function, so **no tool argument a model can populate ever contains a
credential**. Prompt-injection exfiltration is structurally impossible rather than merely
discouraged.

## When things go wrong

| Failure | What happens |
|---|---|
| Missing credential | The task **parks**, the UI names what to connect, and the *same run* resumes once it is connected |
| Process crash mid-task | Resumes from the same step; leases expire after 30s and are reclaimed |
| Repeated tool call | Hash-matched against `tool_calls` and served from the stored result — the side effect fires once |
| Task exhausts retries | The goal is replanned around it |
| Unreachable app | The planner is told which apps have credentials *before* it plans, and routes around the rest |

## Agents cannot report work they did not do

This is the part we would defend hardest, and every guard below exists because a live run
got past the previous ones.

- **A result that admits failure, or carries a failed tool envelope, is rejected.**
- **An invented URL is rejected** — addresses are compared against what tools actually returned.
- **A claim with no artifact is rejected**: "I opened a pull request" with nothing to click does not pass.
- **Unfilled placeholders are refused before publishing.** A plan once handed a Linear description `Bug fix PR: {{t3.output.url}}` — a task referencing its own not-yet-existent output.
- **A pull request may not describe code it did not change.** One run shipped a correct fix under a body about `average`, a function the diff never touched. Every tool returned `ok: true` and every guard passed, because nothing was fabricated — the pull request was simply wrong about itself.
- **A change the description does not account for is refused.** Told "if it is already correct, say so", the pipeline instead opened a pull request adding module-level `assert`s to a library file.
- **A pull request may not say it ran something this run never ran.** The deployed demo opened `mergit-e2e-sandbox#67` with a correct fix and a Verification section reading "Ran the following commands … all outputs are as expected". Nothing ran: `code_exec` is unregistered on that deployment, and the run's tool list proves it. The claim's subject is not the diff, so no existing guard looked there.
- **A pull request may not say the run came back clean when it did not.** The next run got past that guard a different way: `code_exec` *did* run, returned `ok: false` and `FAIL: was able to oversell after double release`, and the body still said "All tests passed" — inside a fenced block, where the previous check deliberately does not look. CI then went red on exactly the test the body named. A run that executes twice, failing first to reproduce and passing after the fix, is still accepted; what is refused is claiming success when nothing in the goal ever exited zero.
- **A run that read a thread must answer in it.** Asked to reply in the Slack thread, one run read the thread, received `ts: 1789286027.409169`, and then posted a new top-level message — reporting success while the person watching the thread saw nothing. The timestamp was in its own tool output two calls earlier, which is the point: the schema already said to reply in-thread, and advice is not a mechanism.

Each finished task is serialised canonically, hashed with SHA-256 and recorded to an
on-chain `ProofOfWork` against the agent's passport. Any proof can be re-checked from the
UI: recompute the hash from the stored output, read the chain, compare. It runs on an
in-process EVM by default; the same code path targets Monad testnet.

## How we know it works

`evals/` runs scenarios against a live server and grades every one by **reading the
services back**. Nothing consults a goal's output, its task rows or its tool results —
those are the claims under test, and a harness that graded claims against themselves would
agree with every lie.

Two numbers, because one hides the difference that matters:

- **Silent failure** — reported COMPLETED, the services say otherwise, and nothing in the run's own output admits it. The dangerous kind: the run nobody goes and checks.
- **Reported shortfall** — missed an objective and *named the one it missed*. There the defect is the COMPLETED status, not the honesty.

The suite runs against a real service — the Northwind Fulfilment codebase in the sandbox
repository: six modules, about a thousand lines that call each other, and eight defects of
deliberately different shapes, each verified by hand before it was written into a scenario.
A harness asserting a bug that is not there measures nothing, twice.

| scenario | what it measures | runs | ok | silent | median |
|---|---|---|---|---|---|
| `ship_the_fix` | the full four-app chain, on a wrong *value* | 2 | 2 | 0 | 169.6s |
| `crash_not_logic` | a bug that raises rather than lying | 2 | 2 | 0 | 87.1s |
| `silent_data_loss` | an import that reports success while dropping rows | 2 | 2 | 0 | 153.2s |
| `already_correct` | nothing to fix; a pull request here is the failure | 2 | 2 | 0 | 26.3s |
| `report_only` | a one-step goal must not become a four-step plan | 2 | 2 | 0 | 75.5s |
| `degraded` | an app with no credential; skipped while that app is reachable | — | — | — | — |

**100% success · 0% silent failure · 859 unit tests.**

`degraded` is reported as a dash rather than folded into the total: both attempts to run it
were ungraded — one opened no pull request and said so, and one could not be graded at all
because unsetting the Notion key for that job also stripped the GitHub token from its
environment. A setup error of mine, not a result, and averaging it into a headline would
be the exact move this document argues against.

Five of the six are deliberately not the happy path, because a suite made only of happy
paths measures whether the demo works rather than whether the system does. Two of them test
skills the original suite never did: `crash_not_logic` gives the agent a traceback instead
of a wrong number, and `silent_data_loss` gives it a job that reports success — there is
nothing to see there unless you read what the code does with what it skipped, which is the
same question this whole brief is about.

## What the suite caught that a demo would not

Every defect fixed since the harness existed was found by the harness:

1. **A tool took its own schema literally.** `notion_create_page`'s description said "Defaults to NOTION_PARENT_PAGE_ID" and a model passed that *string* as the value, shadowing the real default.
2. **Work manufactured out of nothing** — the `already_correct` failure above, twice out of two before it was fixed.
3. **Two fabricated claims, both from live runs, each of which produced a guard** — the execution claim and the clean-run claim above. The second was found by reading a run that had just fixed a real bug correctly: the diff was right, four apps were touched, every tool returned `ok: true`, and the pull request said its tests passed while its own execution said they failed.
4. **Plan references that never resolved.** Templates were replaced only at the top level of a plan's inputs, so `{"data": {"root_cause": "{{t2.output.summary}}"}}` reached the writer as literal text and became finished prose. Two of the three template walkers in the codebase already recursed; the one whose result reaches a tool did not.
5. **Plan references that resolved to the wrong thing.** A missing field falls back to the whole upstream output, so `{{t2.output.summary}}` on a *coder* handed the writer the entire contents of `calc.py` as an incident note's "root cause". Plans are now checked against each agent's declared output schema before they run.

The clearest single run is `8738177b`, where three guards fired in sequence: a pull request
was refused for carrying an empty-input guard nobody asked for, the retry shipped `+1 -1`
instead of `+4 -2` and said so, and the placeholder guard then stopped a Notion page full
of unresolved templates.

## Known limits

- **Slack OAuth is written and tested against a stubbed exchange, never against real Slack.** Every live run used a workspace bot token.
- **Linear and Notion are single-tenant** — the encrypted store, broker and park/resume path are provider-generic, but neither has an OAuth flow yet.
- **The public deployment runs all four apps on shared deployment tokens**, not per-user connections, so it is one workspace rather than one per visitor. It is password-gated for that reason.
- **`code_exec` is unregistered on any public deployment.** It runs model-authored Python in a subprocess of the API server, which is fine on a laptop and not on an open URL.
- **The eval harness waits out its full timeout** when only *some* tasks are parked rather than all of them.
