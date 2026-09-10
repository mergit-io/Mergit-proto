# Multi-App AI Agent Hackathon — build plan

**Event:** virtual, Sunday 13 September 2026. Hosted by [Lemma](https://www.uselemma.ai/) ×
[Comma Capital](https://comma.vc/), judged by the founders of [Arga Labs](https://www.argalabs.com/).

**The brief, verbatim:** *"Build one useful, multi-step AI agent. Connect it to at least
three external apps. Show how you know it works."*

**Judging:** 30% technical execution · 25% reliability & evaluation · 20% usefulness ·
15% originality · 10% demo clarity.

## Why this shape, and not another

Both companies in the room sell the same conviction from different ends. Lemma detects
**silent failures** — agents that report success while having done nothing. Arga builds
**stateful sandbox twins** of Slack, GitHub, Gmail and Stripe, and grades agents by
capturing evidence of *service-state changes*, not by reading the agent's own summary.

Mergit already refuses to let an agent claim work it cannot evidence
(`agent_runner._submission_problem`, `test_fabricated_claims.py`). That is the same
argument, built before we knew who was judging. The plan leans on it rather than adding a
new headline: **the agent works across four apps, and every cross-app action comes back
with an address a human can open.**

The on-chain proof layer stays, demoted to one beat of the demo — a tamper check, not a
thesis. The audience is agent infrastructure, not crypto.

## The apps

| App | Role in the workflow | Status |
|---|---|---|
| **GitHub** | Where the fix lands: fork, patch, PR, review, merge, issues | 24 tools, live |
| **Slack** | Where the work is asked for, and where it is reported back | 5 tools, OAuth + bot-token paths |
| **Linear** | The system of record for whether it is done | 6 tools |
| **Notion** | The written record: what broke, root cause, links | 4 tools |
| *(a website)* | `http_request` confirms the PR preview deploy answers 200 | already present |

## The use case

**Goal sentence:** *"Close the loop on the bug reported in #eng-bugs."*

| Step | App | What proves it — read back from the service, not from the agent |
|---|---|---|
| Read the thread, extract the repro | Slack | `conversations.replies` returns the thread we say we read |
| Write the fix | — | the coder's own execution output |
| Open the PR | GitHub | `GET /pulls/:n` → state, head sha, `Closes #N` |
| Open the ticket, move to In Review | Linear | `issue(id)` → state name, PR URL in the description |
| File the incident note | Notion | `GET /pages/:id` → title and body text |
| Reply in the original thread | Slack | the thread now contains our `ts` and the three URLs |

Order is fixed, and the planner is told why: an announcement scheduled before the artifact
has nothing real to link to, and the artifact guard rejects it.

## Built so far

- `tools/service_client.py` — one credential resolver for all three new services, mirroring
  `tools/github_client.py`: user connection → deployment token → park on
  `WAITING_CREDENTIAL` so the task resumes on the same run instead of failing.
- `credentials/broker.service_token` — generic sealed-token reader. `credentials/` remains
  the only package that can decrypt, which `test_route_coverage.py` enforces.
- `tools/slack_ops.py`, `tools/linear_ops.py`, `tools/notion_ops.py` — 15 tools.
- Registered in `TOOL_REGISTRY`, granted to `researcher` (read) and `integrator` (write),
  and described to the planner in `orchestrator.AGENT_DESCRIPTIONS`.
- `agent_runner._PRODUCES_A_URL` extended, so "I posted it" with no permalink is rejected
  the same way "I opened a PR" with no PR URL always was.
- `tools/placeholders.py` — one unfilled-blank guard, shared by every write tool. A plan
  that hands `{{t3.output.url}}` to a Linear description no longer publishes it.
- `tools/grounding.py` — a pull request body may not claim something about code the diff
  does not touch. See "The run that made this necessary" below.
- `test_multi_app_tools.py` (33) + `test_grounding.py` (10). Suite: **726 passed, 35 skipped**.
- `scripts/multiapp_smoke.py` — one read per service, `--write` for one real write each.
  Currently reports **4/4 apps live**.

## Two live runs, and what they cost

**`0e9fefe4`** stalled at `WAITING_CREDENTIAL: NOTION_API_KEY`. The plan was right and the
system was right to park rather than fake a step — but the planner had no way to know which
of the four apps was uncredentialled. `orchestrator.connected_apps_note` now resolves that
per goal through the same `credential_check` the tools use.

**`0e067775`** completed in 45s and produced PR #47, whose diff was exactly correct —
`biggest = 0` became `biggest = numbers[0]` — under a body that read:

> ## Problem
> The `average` function did not handle empty lists properly

`average` was already correct and the diff never touched it. Every tool returned `ok: true`,
every guard passed, and the Linear ticket carried the same wrong story to In Review. Nothing
was fabricated, so no fabrication guard could see it: the artifact was *wrong about itself*.

Three prompt changes stop it starting (the report is threaded into the integrator's inputs,
the body must be written from the report rather than the diff, and the coder is told to fix
what was reported and nothing else), and `tools/grounding.py` catches it if it starts anyway.

**`1bf7a52f`** is the same goal after the fix: 55s, four apps, PR #48 titled *"fix: correct
largest() to handle all-negative lists"*, ABH-7 In Review, a Notion incident note, and a
Slack reply in the original thread carrying all three URLs.

## How we know it works

`evals/` runs the scenarios against a live server and grades every one of them by reading
the services back. Nothing consults a goal's output, its task rows or its tool results —
those are the claims under test, and a harness that graded claims against themselves would
agree with every lie.

Latest suite, three runs per scenario:

| scenario | runs | ok | silent | said so | median |
|---|---|---|---|---|---|
| ship_the_fix | 3 | 2 | 0 | 1 | 106.2s |
| already_correct | 3 | 3 | 0 | 0 | 25.1s |
| report_only | 3 | 3 | 0 | 0 | 46.0s |
| degraded | skipped — only means something while Notion is unreachable | | | | |

**success 89% · silent-failure 0% · reported shortfall 11%**

Two runs earlier it was 83% / 17%. The 17% was `already_correct` manufacturing work, and it
is now 3 for 3.

Three of the four scenarios are not the happy path, because a suite made only of happy
paths measures whether the demo works rather than whether the system does.

The suite separates two things a single number hides. A **silent failure** is a run
reported COMPLETED that the services say did not happen, with nothing in its own output
admitting it — the dangerous kind, because it is the run nobody goes and checks. A
**reported shortfall** missed an objective and named the one it missed; there the defect is
the COMPLETED status, not the honesty. Run `dcaac2eb` was the second kind, and scoring it
as the first would have slandered an agent that told the truth.

Every finding so far came from this suite rather than from watching a demo:

- **`already_correct` manufactured work** — 2 of 2, then 1 of 2. Told "if it is already
  correct, say so", the pipeline opened PR #52 adding module-level asserts and a `print` to
  a library file, and PR #53 whose own Root Cause section read "No code-level issue was
  found". `tools/scope_creep.py` refuses both; the scenario has passed every run since.
- **`notion_create_page` took its own schema literally.** The description said "Defaults to
  NOTION_PARENT_PAGE_ID" and a model passed that string as the value, shadowing the real
  default. Fixed; `ship_the_fix` went 0/1 → 2/2.
- **The planner still hands unresolved templates downstream.** Run `8738177b` reached
  `notion_create_page` with `{{8738177b_t2.output.summary}}` still in the body. The
  placeholder guard refused to publish it and the run said so — which is the whole of the
  remaining 11%. The guard works; the interpolation bug behind it does not have a fix yet.

Run `8738177b` is also the clearest evidence the guards do their job. Three fired in one
run: `github_pr` refused a first attempt that added an empty-input guard nobody asked for,
the retry shipped `+1 -1` instead of `+4 -2` and said "This PR does not add any new guard
for empty lists", and the placeholder guard then stopped a Notion page full of unresolved
templates.

## Still to build

1. **Receipts** (`receipts.py`) — request hash, response hash and a post-action read-back
   per side effect, over the existing `tool_calls` row (`args_hash`, `result_json`).
2. **Fault injection** — kill the worker mid-run, revoke a token, force a 500. All three
   recovery paths already exist (lease reclaim, `WAITING_CREDENTIAL`, replanner); the
   harness has to prove they fire.
3. **Plan interpolation** — `{{t2.output.summary}}` reaching a tool unresolved is the
   last known cause of a failed objective. The guard catches it; the planner still emits it.
4. `/app/evals` — one table, and the reliability brief writes itself from it.
