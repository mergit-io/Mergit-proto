# Mergit — Product Research, Status & Decision Register

**Purpose of this file.** This is the single document where the product question gets answered —
*what are we building, why, for whom, and what is actually real today* — and where every finalised
and validated plan gets recorded once decided.

- **Parts 1–9 are research.** Written from the code and the live deployment, not from the older docs.
  Every non-obvious claim carries its evidence.
- **Part 10 is the decision register.** The six forks that needed a human call, each kept with its
  rejected alternatives so the reasoning stays reviewable. **All six decided 2026-08-14.**
- **Part 11 is the finalised plan log** — P1–P6, one per decision. Only validated plans go here: a
  plan is "validated" when its assumptions have been checked against the code or a live run, not
  when it merely sounds right. Three of the six changed shape under that check; the assumptions that
  failed are recorded alongside the ones that held.

**Working rule:** new work gets decided in Part 10 and planned in Part 11 before it gets built.
`progress.md` records what happened; this file records what we intend and why.

**Verified:** 2026-08-14, against `mergit.onrender.com`, the local SQLite DB, and the working tree at
`dcbbfae`. Where an older doc disagrees with this one, this one was checked more recently — but
`CLAUDE.md` remains the authority on *how the code works*, and this file on *what we are doing with it*.

**Relationship to the other docs**

| File | Owns | Status |
|---|---|---|
| `CLAUDE.md` | How the code works — the canonical architecture summary | ✅ current (audited 2026-08-14) |
| `docs/REPO_MAP.md` | Which file owns what | ✅ current |
| `progress.md` | Dated changelog, append-only | ✅ current |
| `ROADMAP.md` | Issue register, P0–P3 | ⚠️ **stale framing** — written for "show the manager a demo"; superseded by Parts 6–10 here |
| `EXPLANATION.md` | 5-minute pitch script | ❌ hackathon artifact; claims oversell (see §4.3) |
| `final.md` | **This file** — product definition, ratings, decisions | ✅ authoritative for direction |

---

# Part 1 — What we are building

## 1.1 The one-sentence definition

> **Mergit is a self-hosted autonomy runtime that turns a plain-English goal into completed work on
> GitHub — planning it into a task graph, executing it with tool-using agents, surviving its own
> crashes, and recording a cryptographic proof of every finished task.**

## 1.2 The precise definition (what the code actually is)

Three layers, and it matters that they are separable:

**Layer 1 — The autonomy runtime (the substance).**
A goal enters at `POST /api/goals`. The orchestrator (`orchestrator.py`) makes one forced tool call
that returns a `PlanSchema` — a DAG of tasks, each naming an agent, its inputs, and its dependencies.
The plan is persisted to SQLite before anything executes. Three asyncio loops in `worker.py` drive it:
a planner, an executor (N concurrent, semaphore-bounded), and a reclaim loop that returns
lease-expired tasks to READY every 30s. Every tool invocation is hashed and cached in `tool_calls`,
so a crash mid-goal replays without opening a second pull request. Inputs interpolate across the DAG
(`{{t1.output.summary}}`) so agents genuinely hand work to each other.

This layer is the actual engineering asset. It is ~14.4k lines of backend Python with 331 passing
tests across 25 test files, and it does the thing that is hard: *durable, resumable, idempotent
multi-step execution against a real external system.*

**Layer 2 — The GitHub work surface (the product's hands).**
26 registered tools, **20 of them GitHub**: read a repo, read an issue, read a real unified diff,
open a PR, submit a formal review, merge behind a guard, manage branch protection and Actions.
Four agents with deliberately asymmetric access — `researcher` reads GitHub, `integrator` writes to
it, `coder` executes Python, `writer` produces prose. The split is a safety property, not an
aesthetic one: a researcher cannot open a PR because it does not hold the tool.

**Layer 3 — The proof/economy layer (the differentiator, unproven as a differentiator).**
Every completed task mints `sha256(canonical_json(output))` onto a real EVM — four self-contained
Solidity contracts (`AgentPassport` soulbound, `ProofOfWork` idempotent-by-revert,
`ReputationRegistry` with the ±20% delta cap enforced *in bytecode*, `AuditTrail`). Default runtime is
an **in-process py-evm** — real bytecode, real tx hashes, real receipts, zero keys or network.
`GET /api/economy/verify/{task_id}` recomputes the hash and compares it to the chain, and tampering
with a stored output in SQLite is detected (verified end-to-end, `scripts/demo_tamper.py`).

> **Layer 3 is architecturally decoupled and could be deleted in an afternoon.** `chain/client.py` is
> the only thing the app imports and every method degrades to `None` rather than raising. That is
> worth knowing before Part 10.2 asks whether to keep it.

## 1.3 What it is *not*

Stating this plainly prevents the positioning drift that already put four false claims into the docs:

- **Not a copilot or an IDE plugin.** There is no editor integration and no human-in-the-loop step.
- **Not a framework.** You do not write graphs, chains or Python against it. It is a running service
  with an API and a UI.
- **Not multi-tenant.** The `goals` table has no owner column. One process-global `GITHUB_TOKEN`
  serves every visitor. This is structural, not a config gap (see §8.2).
- **Not a hosted product.** There is no billing, no accounts, no quotas, no per-user isolation.
- **Not currently secured.** See §8.1 — this is the single most important fact in this document.

---

# Part 2 — Why this exists

## 2.1 The problem, stated without the pitch varnish

Most software teams carry a permanent backlog of work that is **individually small, collectively
expensive, and never anyone's priority**: the flaky test nobody owns, the dependency bump, the
one-line null check, the missing CI workflow, the README that drifted two refactors ago, the issue
that a drive-by contributor filed with a perfect reproduction and no follow-up.

The cost is not the work. The cost is the **context switch** — loading a codebase you didn't write
into your head to make a ten-minute change. That is why these items rot for weeks in teams that are
perfectly competent.

## 2.2 Why an agent system is the right shape for it

This class of work has three properties that suit autonomous execution unusually well:

1. **It is verifiable.** A fix either passes the test or it does not. A PR either merges cleanly or
   it does not. Unlike open-ended generation, there is a ground-truth check at the end.
2. **It is reversible.** A pull request is a *proposal*. The single most dangerous action in the flow
   — merge — is the one the code already guards (`github_merge_pr` refuses on conflicts, failing
   checks, or a `CHANGES_REQUESTED` review, and *reports the refusal as a legitimate outcome*).
3. **It is bounded.** A small fix has a small blast radius, which is what makes it acceptable to
   automate before the technology is trustworthy at large scope.

## 2.3 Why *this* implementation rather than a script

The three things that are genuinely hard, and that Mergit has actually built:

| Hard thing | Why it matters | Where it lives |
|---|---|---|
| **Durability** | An agent run that dies at step 4 of 6 and cannot resume is a demo, not a tool. Mergit persists the plan before executing and reclaims expired leases. | `db.py`, `worker.py::reclaim_loop` |
| **Idempotency** | Retry logic plus side effects means duplicate PRs and duplicate comments. Every tool call is hashed and cached; a replayed merge returns `already_merged=True` rather than an error. | `agent_runner.py`, `tools/github_ops.py` |
| **Honest failure** | The recurring bug class in this repo is *silent success* — a green run with the feature off. Six separate fixes now exist purely to make failure visible. | §6.4 |

That third row is the most underrated thing in the codebase and is developed in §4.2.

---

# Part 3 — What it solves, concretely

Rated by **how well the current code actually serves each job** — not by how good the story sounds.

| # | Job story | Pipeline | Fit today | Evidence |
|---|---|---|---|---|
| **J1** | *"An issue was filed with a clear reproduction; fix it and open a PR."* | webhook → researcher → coder → integrator | 🟡 **Wired, lightly proven** | Full pipeline tested with GitHub stubbed (`test_github_automation.py`, 11 tests). One real live run shipped a `stats.py` fix as `+3 −3` after the truncation guard forced a resend. |
| **J2** | *"Review this PR properly — read the diff, not the title."* | researcher (`github_get_pr_files`) → writer → integrator (`github_review_pr`) | 🟢 **Proven** | Was silently blind until 2026-08-13; the real diff tool now exists, budgeted to 12k chars/60 files with truncation reported. |
| **J3** | *"Merge PR #N if it's safe."* | integrator alone | 🟢 **Proven live** | Real run against `mergit-e2e-sandbox` PR #3: agent read the PR, attempted the merge, the guard refused on conflicts, and it **reported the refusal instead of claiming success**. |
| **J4** | *"Research X and write it up."* | researcher → writer | 🔴 **Degraded in production** | `web_search` has **no Tavily key** on the live deployment; the DDG Instant-Answer fallback is not a web index and measurably returns `{"results": []}` for ordinary dev queries. This reduces to "answer from training knowledge". |
| **J5** | *"Set up CI / branch protection on this repo."* | integrator | 🟡 **Wired, never run** | `github_list_workflows`, `github_get_branch_protection`, `github_set_branch_protection` registered; no live run recorded. |
| **J6** | *"Scaffold a new project as its own repo."* | coder → integrator (`github_create_repo`) | 🟡 **Wired, never run** | Tool exists; no live evidence. |
| **J7** | *"Prove to me this output wasn't altered after the fact."* | economy/verify | 🟢 **Proven, but weak demand** | Tampering detection verified end-to-end. Nobody has asked for it — see §10.2. |
| **J8** | *"Mergit broke; fix Mergit."* | self-heal → fix goal | 🟡 **Wired, only ever simulated** | 2 `heal_attempts` rows locally, both `status=simulated`. Deduplication verified (same bug ×3 → one attempt, `seen=3x`). Never filed a real issue. |

**Read of the table:** the GitHub *write* surface is the strongest part of the product and the *research*
surface is the weakest. That is a positioning signal — Mergit is a **GitHub work agent**, not a general
research agent, and the docs that describe it as "any natural-language goal" are describing the
orchestrator's flexibility rather than the product's competence.

---

# Part 4 — Honest competitive position

## 4.1 Where Mergit sits

The autonomous-coding-agent space is crowded and moving fast (GitHub's own coding agent, Devin,
Cursor's background agents, and a long tail of issue-to-PR bots). Competing head-on on *fix quality*
is a losing bet: they have larger models, larger teams, and repo-scale context infrastructure.

⚠️ *Landscape claims here should be re-verified before any external positioning — this analysis is
structural, and the competitive set changes monthly.*

**Three things Mergit has that most of that field does not:**

1. **It is self-hostable and provider-agnostic.** 15 model ids across Groq/Anthropic/OpenRouter,
   switchable per-role from the UI with no restart, with a credential-aware fallback chain. A team
   that cannot send its private repo to a vendor SaaS is a real segment, and it is a segment none of
   the incumbents serve well.
2. **It exposes the machinery.** The live DAG, the per-task tool calls, the SSE log — you watch it
   work rather than waiting on a black box. That is a trust surface, and trust is the actual blocker
   to adoption for autonomous code changes.
3. **The refusal behaviour is a feature.** The merge guard, the truncation guard, `WAITING_CREDENTIAL`
   — Mergit is built around *not* claiming success it didn't achieve. This is unusual and it is
   defensible, because it comes from having been burned six times (§6.4) rather than from a design doc.

**The honest weakness:** context. Mergit reads files one at a time through the GitHub API. It has no
repo index, no embedding store, no memory across goals. For anything beyond a localized fix, the
incumbents' repo-scale context wins decisively.

## 4.2 The strongest strategic asset is the failure discipline

Six separate defects in this repo share one shape — **the run reported success while the feature was
off**:

| # | The silent success | Now caught by |
|---|---|---|
| 1 | Chain reported READY against contracts that did not exist | `eth_getCode` bytecode check |
| 2 | `/api/economy/chain` hardcoded Monad while running on 31337 — and its **test asserted the constant** | endpoint reports the live client |
| 3 | PR reviewer "reviewed" from the PR title, never reading a diff | `github_get_pr_files` |
| 4 | Fix landed in a **new** file beside the buggy one; PR green, nothing fixed | required `path` + `files_created` vs `files_modified` |
| 5 | Model returned only the changed function → PR `+3 −10`, deleted `median()` and the docstring | `_dropped_definitions()` refuses pre-commit |
| 6 | `model_health` was never wired to anything; `all_healthy: true` while nothing worked | hard limits now register cooldowns |

**Two of these were invisible to a passing test suite**, for the same reason: the stubbed tests script
the plan instead of asking a model for one, so the validator never saw a real merge plan and the
reviewer's stub never had to produce a diff. That lesson — *stubs prove wiring, not semantics* — is
worth more than any single feature, and it is why "we ran it live" appears throughout `progress.md`.

## 4.3 Where the current messaging oversells

`EXPLANATION.md` should not be shown to anyone until corrected. Specific defects:

- *"and just built and submitted this pitch autonomously"* — unsupported.
- *"gets smarter about your codebase the more it runs"* — **there is no memory.** No embeddings, no
  repo index, no cross-goal state. This is the single most misleading line in the repo.
- *"sandboxed subprocess"* for `code_exec` — it is `sys.executable -c <code>` with **no sandbox**,
  full filesystem access and every env var inherited (§8.1).
- *"The market is every software company on earth"* — a market-sizing claim that is functionally
  the same as having no target user.

---

# Part 5 — The rating framework

Two axes, because "important" and "real" are different questions and conflating them is how
`ROADMAP.md` ended up rating a live RCE as P3.

### Axis A — NEED (does the product require this to be what it claims?)

| | Meaning |
|---|---|
| **N0 — Existential** | Without it the product is unsafe, illegal to run, or a lie |
| **N1 — Core** | The headline claim depends on it |
| **N2 — Substantive** | Materially better product; not load-bearing |
| **N3 — Optional** | Nice, deferrable indefinitely without cost |

### Axis B — STATUS (how real is it?)

| | Meaning |
|---|---|
| 🟢 **Proven** | Executed against the real thing and observed to work |
| 🟡 **Wired** | Code exists and is unit-tested; never run against reality |
| 🟠 **Blocked** | Code exists; cannot run — missing credential, account, or funds |
| 🔴 **Broken** | Exists and does the wrong thing, or is off in production |
| ⚪ **Absent** | Does not exist |

**Effort** is t-shirt: **S** ≤ half a day · **M** 1–3 days · **L** 1–2 weeks · **XL** > 2 weeks.

---

# Part 6 — Capability register

## 6.1 Core runtime — the part that works

| Capability | Need | Status | Evidence |
|---|---|---|---|
| Goal → DAG planning, 5 retries, Groq-failure salvage | N1 | 🟢 | 23 goals COMPLETED / 67 tasks DONE locally |
| Durable persistence + crash resume | N1 | 🟢 | SQLite WAL, atomic claim via `UPDATE…RETURNING`, lease reclaim |
| Tool-call idempotency | N1 | 🟢 | Hash-cached in `tool_calls`; replayed merge → `already_merged=True` |
| Cross-task interpolation incl. array paths | N1 | 🟢 | `test_e2e_workflow.py` proves `{{t1.output.summary}}` reaches the next agent |
| Per-agent tool scoping (researcher can't open PRs) | N1 | 🟢 | Asserted in `test_e2e_workflow.py` |
| Multi-provider fallback, credential-aware, health cooldowns | N1 | 🟢 | Skips keyless providers; raises the *first* error, which is the explanatory one |
| Live DAG + SSE streaming UI | N2 | 🟢 | React Flow + `EventSource`; stream now terminates on finished goals |
| Replanning after `max_attempts` | N2 | 🟡 | `test_replanner.py` (11 tests); never observed live |
| Self-heal (classify → dedup → issue → fix goal) | N3 | 🟡 | 2 attempts, both `simulated`; never filed a real issue |

## 6.2 GitHub surface — the product's actual value

| Capability | Need | Status | Note |
|---|---|---|---|
| Read repo / file / issue / code search | N1 | 🟢 | Researcher's working set |
| **Read the real unified diff** | N1 | 🟢 | 12k/60-file budget, truncation reported |
| Open a PR (fork fallback, upstream base sha) | N1 | 🟢 | Fork path previously reverted every upstream commit since the fork — fixed |
| **Truncation guard** (`_dropped_definitions`) | N0 | 🟢 | Prevents shipping a fix that deletes the rest of the file. Model-dependent: fires on `llama-3.3-70b`, never on Haiku |
| **Merge guard** | N0 | 🟢 | Live-proven refusal on a conflicted PR |
| Formal review submission, self-review downgrade | N1 | 🟢 | GitHub rejects approving your own PR; the agent usually authored it |
| Issue lifecycle (create/close/label/comment) | N2 | 🟡 | Registered, thinly exercised |
| Actions + branch protection | N3 | 🟡 | Never run live |
| Unified token resolution | N1 | 🟢 | One `github_token()`; previously nine of ten tools disagreed with the tenth |
| Webhook receiver + HMAC verification | N1 | 🟡 | Tested with stubs; **no real webhook has ever fired** |

## 6.3 Proof / chain layer

| Capability | Need | Status | Note |
|---|---|---|---|
| Four Solidity contracts, self-contained | N3 | 🟢 | 17 tests on a real EVM; largest 4842 bytes vs 24576 limit |
| Local in-process EVM (no keys/network) | N3 | 🟢 | Real bytecode, tx hashes, receipts |
| Proof outbox, restart-safe, dead-letters at 10 | N2 | 🟢 | A dead chain delays settlement; it never fails a goal |
| Tamper detection | N3 | 🟢 | `demo_tamper.py`: verify ✓ → edit SQLite → ✗ MISMATCH → restore ✓ |
| **Durable chain (survives restart)** | N3 | 🟠 | Local EVM dies with the process. 54 of 68 local proofs verify as `null` |
| Monad testnet deployment | N3 | 🟠 | **Blocked**: every faucet gates on a mainnet ETH balance |
| Reputation scoring, badges, leaderboard | N3 | 🟢 | Deterministic, no RNG |
| Wallet connection | N3 | 🔴 | **Mock** — deterministic fake `0x` in localStorage |

## 6.4 Security, tenancy, operations

| Capability | Need | Status | Note |
|---|---|---|---|
| **Any authentication in production** | **N0** | 🔴 | `ACCESS_PASSWORD: ""` in `render.yaml`, deliberately. Verified live: `GET /api/config/keys` returns **200** unauthenticated |
| **`code_exec` sandboxing** | **N0** | ⚪ | `sys.executable -c <code>`. No sandbox, no network policy, no fs policy, inherits `GITHUB_TOKEN` and every provider key |
| Shared-secret gate (code exists) | N0 | 🟡 | `access_gate.py` works and is tested — it is simply **switched off** |
| Frontend login | N1 | 🔴 | Firebase exists; `ARG VITE_DEMO_MODE=true` bypasses it in the shipped image |
| Backend OAuth | N2 | 🔴 | **Dead code.** Zero frontend references; no route checks the cookie; scopes (`read:user user:email`) cannot open a PR; tokens discarded after profile read |
| Multi-tenancy | N1 *(if product)* | ⚪ | No owner column on `goals`; one global `GITHUB_TOKEN` |
| `spawn_goal` runaway guard | **N0** | ⚪ | **No depth limit, no parent link, no cycle guard.** Self-heal has `MAX_HEAL_DEPTH=1`; `spawn_goal` inherits nothing |
| Rate limiting / quotas / cost caps | N1 *(if public)* | ⚪ | Nothing. One visitor can drain the entire LLM budget |
| Billing / accounts | N2 *(if product)* | ⚪ | Does not exist |
| Stranded-PLANNING-goal recovery | N2 | 🔴 | `find_orphaned_goals` requires `terminal_task_id IS NOT NULL`; a goal that died before its first task row is invisible forever. Live victim: `f3e6b093` |
| `WAITING_CREDENTIAL` surfaced in UI | N2 | ⚪ | State + resume path exist; no banner tells a human which variable to supply |
| Repo memory / context across goals | N1 *(for J1 quality)* | ⚪ | Does not exist despite `EXPLANATION.md` claiming it |
| Observability (metrics, alerting) | N2 | ⚪ | Structured `llm_call` log lines only |
| Backup / durable data | N2 | 🔴 | Render free has **no disk**; SQLite and the chain reset on every redeploy |

---

# Part 7 — Measured status ledger

All figures measured 2026-08-14, not carried forward from prior docs.

## 7.1 Codebase

| Metric | Value |
|---|---|
| Backend Python (excl. venv) | **14,403 lines** |
| Frontend TS/TSX | **5,947 lines** |
| Test files / test functions | **25 / 366 collected — 331 passed, 35 skipped, 0 failed** (40.5s) |
| Registered tools | **26** (20 GitHub) |
| Executable agents | **4** (`economy.ROLES` lists 6 — `notifier` is a deliberate ghost holding passport #6) |
| Model ids | **15** across Groq (8), Anthropic (5), OpenRouter (2) |
| Python dependencies | 22 |
| Branch / HEAD | `main` @ `dcbbfae`, clean, pushed |

> ✅ **Suite executed 2026-08-14: `331 passed, 35 skipped, 0 failed` in 40.5s.** The
> `pytest-asyncio` concern did **not** materialise — every one of the 35 skips is a deliberate gate
> in `test_live_deployment.py` (`set MERGIT_BASE_URL to run`, `set MERGIT_LIVE_GOAL=1 (spends
> provider quota, writes to the ledger)`), not a silently-skipped `async def`. The suite is honest.
> `progress.md`'s "364" is a stale count, not a regression.

## 7.2 Live production — `mergit.onrender.com`

| Fact | Value |
|---|---|
| Health | `{"status":"ok","db":"ok","worker":"running","chain":"ready","chain_id":31337}` |
| Response time (warm) | 0.41s |
| **Authentication** | **None.** `/api/goals` → 200, `/api/config/keys` → 200, both unauthenticated |
| Keys set | `GROQ_API_KEY` ✅ · `OPENROUTER_API_KEY` ✅ · `GITHUB_TOKEN` ✅ (`Mergit-bot`) |
| Keys absent | `ANTHROPIC_API_KEY` ❌ · `TAVILY_API_KEY` ❌ (⇒ web search is dead in prod, J4) |
| Goals in prod DB | **2** — 1 seeded COMPLETED, 1 FAILED |
| Proofs confirmed | 3 (all from `SEED_DEMO` on the current boot) |
| Self-heal attempts | 0 |
| Chain | Local in-process EVM (31337), 4 contracts, wiped every restart |

> **The honest read: production has effectively zero real usage.** The instance is a warm,
> continuously-reset demo. Every "it works" claim in this repo rests on local runs and a handful of
> live GitHub runs — not on production traffic.

## 7.3 Local DB — where the real evidence lives

| Metric | Value |
|---|---|
| Goals | 23 COMPLETED · 4 FAILED · 1 PLANNING (stranded, `f3e6b093`) · 1 RUNNING |
| Tasks | 67 DONE · 3 FAILED · 1 PENDING · 1 `WAITING_CREDENTIAL` |
| Per agent (runs/done) | researcher 19/19 · integrator 21/17 · coder 17/16 · writer 13/13 · notifier 2/2 *(historical)* |
| Proofs | 68 minted · 14 confirmed on chain (54 unverifiable — the EVM that minted them is gone) |
| Heal attempts | 2, both `simulated` |

**Integrator is the weakest link by success rate: 17/21 (81%)** — which is exactly the agent that
touches the real world. Worth watching.

## 7.4 Capacity — measured, not estimated

Container throttled to `--cpus 0.1 --memory 512m`, 10 concurrent users holding SSE open while
polling all six dashboard endpoints every 5s:

> **348 requests · 0 errors · p50 300ms · p95 1.3s · 250 MB of 512 MB.** Unthrottled p95 = 265ms.

CPU is not the ceiling. §8 is.

---

# Part 8 — Structural constraints

These are not bugs. They are properties of the current architecture, and each one has a price to
remove. Any plan that ignores them will fail.

## 8.1 🔴 The live deployment is remote code execution as designed

Not a hypothetical, and not a bug — a documented, committed decision (`2588c9a chore(render): turn
the access gate off by setting an empty password`).

**The chain:** `POST /api/goals` is unauthenticated → the orchestrator may plan a `coder` task →
`code_exec` runs `sys.executable -c <arbitrary python>` → in the same process that holds
`GITHUB_TOKEN`, `GROQ_API_KEY` and `OPENROUTER_API_KEY` → with write access to `Mergit-bot`'s
repositories. Separately, `PUT /api/config/keys` lets any visitor **overwrite** the provider keys.

`render.yaml` states this in a comment. `access_gate.py`'s own docstring states it. The gate is
written, tested, and turned off.

**Three things make this worse than it sounds:**
- The URL is guessable and the instance is warm.
- There are **no rate limits or cost caps** — one visitor can drain the LLM budget.
- `spawn_goal` has **no depth limit** — one prompt can create goals that create goals, unbounded.

**This is the N0 item in the entire document.** Nothing else in Part 10 should be decided before it.

## 8.2 Exactly one instance, permanently

Worker loops live inside the FastAPI lifespan, SQLite is a local file, and the EVM is in-process.
Two replicas = two planners racing over a database they cannot share. **No autoscaling. No
`--workers 2`.** Removing this means externalising the queue (Postgres/Redis), splitting the worker
from the API, and dropping the in-process EVM — an **XL** change, and the true fork between "a tool
that runs on one box" and "a hosted service".

## 8.3 Single-tenant by data model

No owner column on `goals`; one process-global `GITHUB_TOKEN`. "Sign in with Google" cannot, even in
principle, grant a per-user GitHub identity — each tool needs its own OAuth app, its own scopes, and
its own stored token. Multi-tenancy is **L–XL** and touches auth, schema, the token resolver, and
every API route.

## 8.4 No memory, no repo context

Files are read one at a time through the GitHub API. No index, no embeddings, no cross-goal state.
This is the hard ceiling on **fix quality** for J1 and the clearest gap versus the incumbents.

## 8.5 Free-tier physics

70s cold start (contracts deploy during it) · 15-min idle sleep, mitigated by a cron ping · **no
persistent disk** — SQLite and the chain reset on every redeploy, which is why `SEED_DEMO` exists ·
Groq's free RPM/TPM is the real throughput ceiling, hence `MAX_CONCURRENT_TASKS=3`.

## 8.6 Model-dependent correctness

The truncation bug (`+3 −10`, `median()` deleted) fires on `llama-3.3-70b` — the model production
runs — and **never** on Claude Haiku from an identical prompt. Prompting does not close it; the
`_dropped_definitions` guard does. **Assume every quality claim is model-specific until proven
across models.**

---

# Part 9 — Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Public URL exploited — key theft, RCE, `Mergit-bot` repo abuse | **High** | **Severe** | §10.1 |
| R2 | Runaway `spawn_goal` recursion drains quota or fills the DB | Medium | High | Depth limit + parent link (**S**) |
| R3 | An agent ships a bad change to a real repo | Medium | High | Guards exist; keep merge gated, never auto-merge to a default branch |
| R4 | A leaked credential ends up in a PR or an issue body | Low | Severe | No output scanning exists today |
| R5 | Silent-success class recurs in an unguarded area | **High** | Medium | Live runs, not stubs (§4.2) |
| R6 | Free-tier data loss surprises a real user | High | Medium | Honest UI labelling, or a paid disk |
| R7 | Direction drift — building features with no target user | **High** | High | This document; Part 10 |

---

# Part 10 — Decision register

**D1–D6 decided 2026-08-14. D7 added 2026-08-15.** The options and trade-offs are kept below as the
record of *why* each call was made — a decision without its rejected alternatives is not reviewable.
The resulting validated plans are in Part 11.

| # | Decision | Chosen |
|---|---|---|
| D1 | Live RCE | **C** — gate writes, open reads (**A** as same-hour stopgap) |
| D2 | Chain layer | **B** — durable via anvil |
| D3 | Target user | **C** — solo dev / self-hosted (**B** as destination) |
| D4 | Next milestone | **all four**, sequenced A → B → E → C |
| D5 | Web search | **C** — add the key *and* narrow the pitch |
| D6 | Hosting | **A** — stay on Render free (B/C deferred; Oracle blocked on card verification) |
| D7 | Durable storage on a $0 budget | **A** — SQLite + Litestream → Backblaze B2, keys moved into the DB |

---

## D1 — 🔴 Close the live RCE · **DECIDED: C** (+ A as stopgap) → P1

**Not really optional — only the shape is.** Options:

| Option | Effort | Result |
|---|---|---|
| **A. Set `ACCESS_PASSWORD`** | **S** — one dashboard variable | Whole surface gated behind HTTP Basic. Loses the "click the link and try it" demo. The prior attempt used `generateValue: true` and locked the operator out — set a *known* value this time. |
| **B. Take the deployment down** | S | Zero risk, zero shop window. |
| **C. Gate writes only, leave reads open** | M | Public dashboard/ledger, gated `POST /api/goals` and `PUT /keys`. Best demo-to-risk ratio; needs a per-route allowlist. |
| **D. Sandbox `code_exec` + rate-limit, stay open** | L | Preserves the open demo properly, but "sandbox arbitrary Python" is not an afternoon's work. |

**Recommendation: C now (M), with A as the same-hour stopgap (S).** Reads are the demo; writes are
the danger. Rotate `GITHUB_TOKEN` and both LLM keys regardless — they have sat behind an open
endpoint for an unknown period.

---

## D2 — The chain/proof layer: keep, cut, or reframe? · **DECIDED: B** → P2

The most distinctive thing in the repo and the least demanded. Cleanly decoupled — `chain/client.py`
is the only import surface and every method degrades to `None`.

**The case for keeping:** genuinely novel; tamper-evident audit of autonomous work is a real
compliance-shaped story ("prove this agent's output wasn't altered"); the contracts are done and
tested; ~zero maintenance cost as-is.

**The case for cutting:** no user has asked for it; it complicates every explanation of the product;
it invites "is this a crypto project?", which repels part of the target market; the local EVM's
proofs die on restart, which is worse than no ledger because it *looks broken*.

| Option | Effort | Result |
|---|---|---|
| **A. Keep as-is (local EVM)** | 0 | Free, but 54/68 proofs verify as `null` after a restart |
| **B. Make it durable with `anvil`** | **M** | Real RPC, real tx hashes, **survives restarts**; byte-identical code path to Monad, so Monad later is a config change. No faucet needed |
| **C. Reframe as "audit log", drop the chain word** | M | Same tamper-evidence via a hash chain; loses the differentiator and the crypto baggage together |
| **D. Delete it** | S | Simplifies the story; discards ~2 weeks of work and the only truly novel component |

**Recommendation: B.** It costs a day, removes the "looks broken" failure mode, and keeps the option
open. Decide A-vs-D only once someone outside the project has reacted to the pitch. **Do not chase
Monad testnet** — every faucet gates on a mainnet ETH balance, and it buys narrative, not capability.

---

## D3 — Who is the target user? · **DECIDED: C now, B as destination** → P3

| Option | Buys | Costs | Unlocks / needs |
|---|---|---|---|
| **A. OSS maintainer drowning in issues** | Sharpest pain, public repos (no privacy blocker), viral surface | Notoriously won't pay | Repo memory, per-repo config; auth matters less on public repos |
| **B. Small team that can't send code to a vendor** | Self-hosting is a *real* moat here; willingness to pay | Enterprise-shaped sales, slow | **Auth + multi-tenancy (§8.2/8.3)** — the XL path |
| **C. Solo dev / personal automation** | Ships today; single-tenant is *correct*, not a gap | Small market, weak monetisation | Almost nothing — this is what exists now |
| **D. Nobody — portfolio/reference project** | Total freedom, no obligations | No feedback loop, no forcing function | Nothing |

**Recommendation: C now, B as the destination.** C is honest about what exists (single-tenant,
self-hosted, one token) and costs nothing to declare. B is where the money is but demands §8.2 and
§8.3 — do not start that until a real user has said yes. A is the best *distribution* channel for
either.

---

## D4 — What is the next real milestone? · **DECIDED: all four, sequenced** → P4

| Option | Effort | Why |
|---|---|---|
| **A. Security & safety hardening** (D1 + spawn depth + rate limits + key rotation) | M | Removes the only *existential* risk. Nothing else is safe to build on top of an open RCE |
| **B. Prove J1 end-to-end on a real repo** (real webhook, real issue, real merged PR) | M | Turns the flagship claim from "wired" to "proven". Currently **no real webhook has ever fired** |
| **C. Repo memory / context** | XL | The real quality ceiling (§8.4) — but premature before B proves the flow is worth improving |
| **D. Multi-tenancy + auth** | XL | Only if D3 = B |
| **E. Docs & positioning cleanup** | S | `EXPLANATION.md` has four false claims (§4.3); `ROADMAP.md` is stale-framed |

**Recommendation: A → B → E, then reassess.** A is non-negotiable. B is the highest-information
experiment available — one real webhook-driven fix tells us more than another month of features.

---

## D5 — Fix `web_search`, or narrow the product? · **DECIDED: C — both** → P5

Production has no Tavily key, so J4 silently degrades to "answer from training knowledge".

| Option | Effort | Result |
|---|---|---|
| **A. Add a Tavily key** | **S** | J4 works; keeps the "any goal" claim honest |
| **B. Drop the research pitch, own "GitHub work agent"** | S (docs) | Sharper positioning; matches §3's evidence |
| **C. Both** | S | Working search *and* honest positioning |

**Recommendation: C.** The key is nearly free and the positioning should narrow regardless — §3
shows the GitHub surface is where the competence actually is.

---

## D6 — Deployment posture · **DECIDED: A — stay on Render free** (B or C later) → P6

| Option | Effort | Result |
|---|---|---|
| **A. Stay on Render free** | 0 | Free; no disk, 70s cold start, data resets each deploy |
| **B. Render paid + disk** | S (money) | Durable SQLite and chain; kills a whole class of confusion |
| **C. Own box (Oracle x86 / VPS)** | M | Persistent, always on, `compose.yaml` + Caddyfile already target it. Oracle blocked on card verification. **ARM will not build** — solcx downloads an x86 solc with no arch check |
| **D. Local only** | S | Zero exposure; zero shop window |

**Recommendation: A until D3 is answered, then B or C.** Paying for durability before knowing who
it's for is premature — but note that D2-B (anvil) and D6-A conflict: an ephemeral host wipes anvil's
state too, so durable proofs really need B or C.

> **Corrected 2026-08-15.** This heading previously read *"DECIDED: A — own box / VPS"*, which
> contradicts its own table (A **is** "stay on Render free"; the own-box option is C) and its own
> recommendation line. The summary table in Part 10 carried the same error. Both now say Render.
> Anyone who read only the heading would conclude the project had moved off Render. It has not.

---

## D7 — Durable storage on a $0 budget · **DECIDED: A** → P7

**Forced by D3-B.** Multi-tenancy (the auth plan, 2026-08-15) makes ephemeral storage untenable in a
way it never was for a single-tenant showcase. A demo that loses its goal history on redeploy is
merely embarrassing; a product that loses **other people's encrypted OAuth refresh tokens** silently
disconnects every user and makes every paused goal unresumable. The auth plan assumed Render
`starter` + a 1 GB disk (≈$7.25/mo). There is no funding, so the budget is **exactly $0**.

**Three facts constrain the answer, and each one eliminates a family of options:**

1. **The durable set is bigger than `mergit.db`.** `/data` also holds `/data/config/.env` — the file
   `PUT /api/config/keys` writes — so **provider API keys saved through the Models page are already
   being lost on every redeploy today**. Only keys set in Render's own dashboard survive. Any answer
   that protects the database and not that file solves half the problem.
2. **`db.py` is 1,036 lines of raw, SQLite-specific SQL.** 10 × `RETURNING` (including
   `claim_ready_task`, the atomic claim the entire worker rests on), 2 × `json_each` in the
   dependency subqueries, `INSERT OR IGNORE`, `PRAGMA journal_mode=WAL`, and `executescript`. No ORM,
   no alembic, `aiosqlite` is the only driver. Moving engines is not a config change.
3. **The workload is always-on.** `poll_interval_seconds = 1.0` means ~2.6M queries/month, forever.
   Free tiers metered in compute-hours with scale-to-zero are sized for apps that idle. This app
   never idles, so 730 hours/month is the number every quota must be checked against — not the
   marketing figure.

| Option | $/mo | Effort | Result |
|---|---|---|---|
| **A. SQLite + Litestream → Backblaze B2** | **0** | **S** | Continuous WAL replication out-of-band; restore on boot. **Zero SQL changes.** Single-writer is Litestream's supported model and §8.2 makes it permanent anyway. RPO = the sync interval. |
| **B. Turso / libSQL** | 0 | M | Keeps most SQLite syntax, but "SQLite-compatible" is a spectrum and the gaps land on `RETURNING` + `json_each` — the hot paths. Row-read quota vs 2.6M polling queries is the open question. |
| **C. Free Postgres (Neon / Supabase)** | 0 | **L** | Spends the 4–13 day port the auth plan deliberately deferred, *and* most free tiers cap compute-hours below 730. Pays the full cost and may still not run 24/7. |
| **D. Render `starter` + 1 GB disk** | 7.25 | 0 | The correct engineering answer, unavailable until there is $7.25. |
| **E. Own box (Oracle / VPS)** | 0 | M | Dissolves the problem — real disk, zero code change. Blocked: Oracle card verification (D6-C), and the user has confirmed Render is the deployment target. |

**Recommendation: A**, with one addition that makes it whole: **move the provider keys out of
`/data/config/.env` and into `mergit.db`, encrypted with the `crypto/envelope.py` the auth plan is
already building for OAuth tokens.** Provider keys and OAuth tokens are the same shape of secret and
deserve the same store. Once they are in the database, `/data/config` needs no durability, Litestream
protects exactly one file — which is what it is designed for — and `/data/workspace` stays ephemeral,
correctly, because it is per-goal scratch for `file_ops`.

**Why A over B and C.** A is the only option that changes no SQL at all, which matters more here than
anywhere else in the codebase: `claim_ready_task`'s `UPDATE … WHERE id=(SELECT … LIMIT 1) RETURNING *`
is correct under SQLite's single-writer WAL model, and a naive translation to
`SELECT … FOR UPDATE SKIP LOCKED` introduces a double-execution race. For the integrator agent, a
double-executed task means a duplicate pull request or a second merge attempt **on a user's
repository**. That risk is not worth taking to save $7.25/month. A also keeps the network out of the
request path — a hosted DB puts a millisecond hop inside a loop that runs every second, whereas
Litestream replicates out-of-band and an R2 outage degrades to "replication is behind", not "the app
is down".

**What we give up, stated plainly.** RPO is the sync interval, not zero. Render free's 15-minute idle
sleep and ungraceful container kill mean the last interval can be lost. Restore-on-boot adds to an
already ~70s cold start. And this does nothing for the in-process EVM, so D2-B (durable proofs via
anvil) remains unsolved and still conflicts with D6-A.

**Resolved 2026-08-15 — the target is Backblaze B2, not R2.** The open question was whether
Litestream's operation volume would exhaust a free object-storage quota. Measured rather than
estimated:

- **The 1 Hz polling contributes nothing.** All three worker loops issue
  `UPDATE … WHERE <predicate matching nothing>` when idle, which dirties no page and appends no
  WAL frame. 2,000 no-op claim+commit cycles grew the WAL by **0 bytes**; one real write grew it
  by 4,152. Litestream bills write transactions, not queries, so the ~2.6M monthly statements are
  free. The bill is set by Litestream's own compaction timers, not by the workload.
- **The measured cost is ~76,400 Class A operations/month** (60 object-writes/hour idle, ~163 per
  goal, at 200 goals/month). Against R2's 1,000,000 that is 7.6% — R2 would have worked.
- **B2 wins because it has no ceiling at all.** Backblaze's Class A, B *and* C transactions are
  free with no daily cap. (The widely-cited "2,500/day" limit is **Class D** — event notifications
  — which this design never uses. That correction is what decided it.) Given that Oracle already
  blocked this project on card verification, the option with no quota to exhaust is the right
  default. Both providers are served by the same config; only endpoint and region differ.
- **Graceful shutdown gives RPO 0 on a redeploy**, verified both ways: a row written 1 second
  before SIGTERM survived the restore; the same write under SIGKILL was lost. This depends on two
  things being exec-form — the `CMD` and the uvicorn invocation — because a shell in either
  position swallows SIGTERM and silently disables the final sync.

**One correction to the durability story, and it is not a small one.** Litestream requires exactly
one writer. `final.md` §8.2's "exactly one instance, permanently" stops being an incidental
consequence of the architecture and becomes a constraint the data now actively depends on. If the
Postgres tripwire's real trigger was ever "we need a second replica", that is now a wall rather
than a slope — hitting it means the Postgres port *and* a hosting change in the same sprint.

**Also shipped alongside it:** `CREATE INDEX idx_goals_status ON goals(status, created_at)`
(migration 006). `claim_new_goal` ran once a second, forever, as `SCAN goals` plus a sort of every
goal ever created — O(goals), and goals are never deleted. Verified locally: the plan becomes
`SEARCH goals USING INDEX`. Unrelated to storage, found while measuring it, and it removes the
only thing in the hot path that degraded with database size.

**Trigger to revisit:** the first paying user, or the first real data-loss incident — whichever comes
first. At that point D is $7.25/month and takes zero engineering, and it is the right answer.

---

---

# Part 11 — Finalised & validated plans

A plan enters this section only when (a) the Part 10 decision is explicit, and (b) its assumptions
have been **checked against the code or a live run**. Each entry records the validation performed —
including assumptions that turned out to be **wrong**, because those are the ones that would have
sunk the plan silently.

**Validation pass run 2026-08-14.** Three of the six plans changed shape as a result. The full suite
was executed as part of it: `331 passed, 35 skipped, 0 failed`.

---

## P1 — Close the live RCE *(D1-C · N0 · effort M · do first)*

### What was validated

| Assumption | Result |
|---|---|
| `access_gate.py` can express a read/write split | ⚠️ **Partly.** It gates on `request.url.path in OPEN_PATHS` — an **exact-match frozenset with one entry** (`/api/health`). There is no method awareness and no prefix matching. The middleware needs extending, not just configuring. |
| SSE survives a gate | ✅ Streams are `GET`, and the browser attaches Basic credentials to `EventSource` itself. |
| Webhooks can be gated | ❌ **No.** GitHub cannot send Basic auth. `POST /api/webhooks/github` **must** stay open. |
| The webhook is safe to leave open | 🔴 **No — and this is the finding that reshapes the plan.** `api/github_webhook.py:23-26`: `_verify_signature` **returns `True` when no secret is configured** ("no secret configured — allow all"). `GITHUB_WEBHOOK_SECRET` appears in **neither `config.py` nor `render.yaml`**, so it is unset everywhere. |

> ### 🔴 The hole the obvious plan would have left
> Gating writes while leaving the webhook open — which is *mandatory*, since GitHub cannot
> authenticate — reopens the **exact same RCE path**: forge an `issues.opened` payload → a goal is
> created → the orchestrator may plan a `coder` task → `code_exec` runs arbitrary Python next to
> `GITHUB_TOKEN`. The write gate would have looked complete and closed nothing.
>
> **Therefore `GITHUB_WEBHOOK_SECRET` is not an optional extra in this plan — it is the plan.**

### Steps

1. **Stopgap, same hour (D1-A):** set `ACCESS_PASSWORD` to a **known** value in the Render dashboard.
   Not `generateValue: true` — that is what locked the operator out last time.
2. **Rotate all three exposed credentials** — `GITHUB_TOKEN`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`.
   They sat behind an open endpoint for an unknown period; assume disclosure.
3. **Make the webhook secret mandatory.** Add `github_webhook_secret` to `config.py`; invert
   `_verify_signature` to **fail closed** when unset *and* not in local dev. Set the secret on the
   deployment and in the GitHub repo webhook config.
4. **Extend `access_gate.py`** from an exact-match `OPEN_PATHS` set to a policy: an explicit
   read-allowlist open to `GET`/`HEAD` (dashboard, economy, ledger, heal, streams), everything else
   gated. `POST /api/webhooks/github` is open *by HMAC, not by password*.
5. **Gate `GET /api/config/keys` despite it being a read.** Masked values still enumerate which
   providers are configured — that is reconnaissance, not dashboard content.
6. Tests first, RED: unauthenticated `POST /api/goals` → 401; unauthenticated `GET /api/economy/proofs`
   → 200; unsigned webhook POST → 401; correctly-signed webhook → 202.

### Exit criteria
Against the live URL: reads 200 unauthenticated · `POST /api/goals` 401 · `PUT /api/config/keys` 401 ·
`GET /api/config/keys` 401 · unsigned webhook 401 · signed webhook creates a goal · `/api/health` 200
(the container healthcheck sends no credentials and must not be gated).

---

## P2 — Durable proofs via anvil *(D2-B · N3 · effort M)*

### What was validated

| Assumption | Result |
|---|---|
| Adding a network is data-only | ✅ **True as advertised.** `chain/networks.py`'s docstring claims "a data change, not a code change" and the code backs it: `NETWORKS` is built from a tuple and `client`/`deployer`/API all read through `get_network()`. |
| `is_local=False` gives the right runtime behaviour | ✅ **For free.** `main.py:73` auto-deploys only when `is_local`; `chain_worker.py:55` requeues confirmed proofs on boot only when `is_local`. An anvil entry with `is_local=False` therefore gets explicit deploy + no spurious requeue without touching either file. |
| anvil is durable out of the box | ❌ **No — this would have sunk the plan.** anvil is **in-memory by default**. Without `--state <file>` (load-and-dump) a restart wipes it *exactly* like py-evm, and D2 would have bought nothing while costing a day. |
| anvil's chain id is safe to use | ❌ **Collides.** anvil defaults to **31337 — the same id as `LOCAL`**. Deployment records are keyed `deployments/{chainId}.json`, and `by_chain_id()` returns the first match, so the two targets would overwrite and shadow each other. **Run anvil with `--chain-id 31338`.** |
| The deployment record survives | ⚠️ **Not in a container.** `chain/registry.py:13` hardcodes `DEPLOYMENTS_DIR = <backend>/deployments` — inside the image, not on `/data`. Must be bind-mounted (or the record committed; addresses are public, not secret). Note `.gitignore:53` ignores `31337.json` *specifically*, so a `31338.json` is tracked by default. |
| `CHAIN_PRIVATE_KEY` is usable | ❌ The value in `.env` is **42 chars — an address, not a key** (already known, `ROADMAP.md` 2.3). anvil prints ten funded accounts with real 66-char keys; use one. Testnet-only, never fund it. |

### Steps
1. Add an `ANVIL` entry to `NETWORKS` — `chain_id=31338`, `is_local=False`, `rpc_url` from env, no explorer.
2. Add an `anvil` service to `compose.yaml` with `--chain-id 31338 --state /state/anvil.json` and a
   named volume. **The `--state` flag is the entire point of this plan.**
3. Bind-mount `backend/deployments/` to the persistent volume (or commit `31338.json`).
4. Set a real 66-char `CHAIN_PRIVATE_KEY` from anvil's funded accounts.
5. Deploy once, explicitly: `scripts/deploy_contracts.py --network anvil --dry-run`, then live.

### Exit criteria
Mint a proof → `verified: true` → **restart the whole stack** → the *same* proof still returns
`verified: true` with its original tx hash. That is the one thing the local EVM cannot do, and the
only result that justifies the work.

---

## P3 — Position as solo-dev / self-hosted *(D3-C · effort S)*

**Decided:** describe what exists — single-tenant, self-hosted, one `GITHUB_TOKEN`, one box — with
"small team, privacy-constrained" (D3-B) as the destination, **not** started until a real user asks.

**Validated:** single-tenancy is structural, not a config gap. `sqlite3 .schema goals` confirms **no
owner column**; `tools/github_client.py::github_token()` resolves one process-global token. Moving to
D3-B is the XL rework in §8.2/§8.3 — correctly deferred.

**Consequence:** stop calling single-instance and single-token *limitations*. For the chosen user they
are **correct design**. §8.2/§8.3 stay documented as the price of the D3-B destination, not as debt.

---

## P4 — Milestone sequence *(D4 · all four selected)*

Sequenced by dependency, not preference. Each gate must hold before the next starts.

| Order | Milestone | Effort | Gate before starting |
|---|---|---|---|
| **1** | **Safety** — P1, plus a `spawn_goal` depth limit, rate limits, cost caps | M | none — start here |
| **2** | **Prove J1 on a real repo** — real webhook → real issue → real fix → real merged PR | M | P1 done (step 3 *is* the webhook secret this needs) |
| **3** | **Docs & positioning** — P5, and the §4.3 false claims | S | after 2, so the docs describe an observed run |
| **4** | **Repo memory / context** | XL | after 2 — never optimise a flow not yet proven worth improving |

**Validated for milestone 1:** `tools/spawn_goal.py` calls `db.create_goal()` directly and records
**no parent, no depth, no cycle guard**. `self_heal` has `MAX_HEAL_DEPTH=1`; `spawn_goal` inherits
nothing from it. One prompt can spawn goals that spawn goals, unbounded — and after P1 the webhook
is the reachable trigger for it, so this belongs in the same milestone as the gate.

**Validated for milestone 2:** no real webhook has ever fired at this system. This is the
highest-information experiment available and it is gated on P1 step 3 — which is convenient, not a
conflict: the secret that closes the hole is the same secret the real webhook needs.

---

## P5 — Web search: fix and narrow *(D5-C · effort S)*

**Both halves, as decided.**

1. **Add `TAVILY_API_KEY`** to the deployment. Validated as a real gap: `GET /api/config/keys` on the
   live instance returns `"tavily": {"set": false}`, so J4 currently degrades to a
   training-knowledge note — measurably, the DuckDuckGo Instant-Answer fallback returns
   `{"results": []}` for ordinary developer queries.
2. **Narrow the pitch to "GitHub work agent."** Part 3's evidence supports it: the GitHub write
   surface is 🟢 proven (J2, J3) while research is the weakest job story regardless of search quality.

Folds into milestone 3.

---

## P6 — Move to an own box / VPS *(D6-A · effort M)*

**Validated:** `compose.yaml` + `deploy/Caddyfile` already target exactly this — app + Caddy, a
`mergit_data:/data` volume, `DB_PATH`/`WORKSPACE_DIR`/`RUNTIME_CONFIG_DIR` all pointed at `/data`.
No anvil service yet (P2 adds it).

**Blocking constraint, unchanged:** ⚠️ **must be an x86 shape.** `solcx/install.py::_get_os_name()`
maps every Linux to one target and downloads `linux-amd64` with no CPU-arch check, so ARM64 fetches
an x86 ELF that cannot exec. Oracle's ARM Always Free tier **cannot build this image**; Oracle's x86
shape is blocked on card verification, so any cheap x86 VPS is the path.

**Why this and not Render paid:** it is the same posture the product is being sold as (D3-C
self-hosted), it removes the 70s cold start and the 15-minute sleep, and it is the only option where
P2's anvil state and P1's persistent config genuinely survive.

**Sequencing note:** P6 and P2 are one move. Doing P2 on Render free would wipe anvil's state on
every redeploy and buy nothing — the two decisions are coupled, and P6 must land first or alongside.

---

## Execution order

```
P1 (gate + webhook secret + rotate keys)   ← N0, nothing else is safe until this lands
  └─ spawn_goal depth limit, rate limits, cost caps
       └─ P6 (x86 VPS)  ─┬─  P2 (anvil, --state, --chain-id 31338)
                          └─  Milestone 2: prove J1 with a real webhook
                                └─ P3 + P5 + §4.3 doc corrections
                                     └─ Repo memory (XL, reassess first)
```

**One thing to carry into every step:** stubs prove wiring, not semantics (§4.2). Each exit criterion
above is written as a *live* observation for that reason.

---

# Appendix A — Evidence log

Commands and observations behind the numbers above, so any claim can be re-checked.

| Claim | How it was verified |
|---|---|
| 14,403 backend LOC / 5,947 frontend LOC | `find … -name "*.py" \| xargs wc -l` (venv/workspace excluded) |
| 25 test files / 314 test functions | `ls test_*.py \| wc -l`; `grep -h "^def test_\|^async def test_" test_*.py \| wc -l` |
| Live health, chain 31337 | `curl https://mergit.onrender.com/api/health` |
| **Unauthenticated `/api/config/keys` → 200** | `curl https://mergit.onrender.com/api/config/keys` — returned masked keys with no credentials |
| Prod key inventory | same response: groq ✅, openrouter ✅, github ✅, anthropic ❌, tavily ❌ |
| Prod has 2 goals | `curl …/api/goals?limit=100` |
| Local DB counts | `sqlite3 backend/mergit.db "select status, count(*) from goals group by status"` (+ tasks, proofs, proof_outbox, heal_attempts) |
| `goals` has no owner column | `sqlite3 … ".schema goals"` |
| `code_exec` is unsandboxed | `backend/tools/code_exec.py` — `asyncio.create_subprocess_exec(sys.executable, "-c", code)` |
| `spawn_goal` has no depth guard | `backend/tools/spawn_goal.py` — calls `db.create_goal` directly, records no parent |
| Access gate deliberately off | `render.yaml` — `ACCESS_PASSWORD: ""` with an explanatory comment; commit `2588c9a` |
| 4 agents, 6 `ROLES` | `backend/agent_registry.py` vs `backend/economy.py:19` |
| Load-test figures | `backend/scripts/loadtest.py`, recorded in `progress.md` 2026-08-13 |

**Not verified for this document** (flagged rather than assumed): the test suite was not executed —
314 functions counted statically vs 364 reported passing in `progress.md`; and no live goal was
submitted, so no end-to-end run was observed today.
