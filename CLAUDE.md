# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Update Protocol

After every piece of work completed in this repo, update **both** files:
- `CLAUDE.md` — keep architecture section current (models, new files, changed behaviour)
- `progress.md` — append a new dated session block describing what was built/fixed

`ROADMAP.md` is the issue register: every open item, rated P0–P3, with what unblocks it. Check an
item off there when you fix it — and verify against the live DB before trusting its status, since
two entries were already stale when it was written.

`docs/REPO_MAP.md` maps every file to what it owns, plus where the docs live and which of them are
stale. The Architecture section below is a summary, not a full inventory — it omits ~10 modules
that the map lists.

---

## Commands

```bash
# Setup (first time)
make install                # creates backend/.venv + installs Python deps + npm install

# Development (two terminals, or run together)
make dev-backend            # backend on :8000 (cd backend && .venv/bin/python main.py)
make dev-frontend           # frontend on :3000 with /api proxy to :8000

# Or both at once
make dev

# Build frontend for production (served by FastAPI at /)
make build

# Reset database
make reset-db
```

The backend venv is at `backend/.venv/`. Always use `.venv/bin/python` for backend work.

---

## Architecture

Mergit is a generic multi-agent autonomy system: a user submits any natural language goal, the orchestrator decomposes it into a task DAG, and specialized worker agents execute each task using tools, with full persistence for restart-resumability. Layered on top is a simulated agent economy — every completed task mints a proof and bumps its agent's reputation on a visually-simulated Monad chain.

### Backend (`backend/`)

**Entry point**: `main.py` — FastAPI app with lifespan that initializes DB, starts the worker, registers all routers, and optionally serves the frontend static build.

**Core execution loop** (`worker.py`):
- `goal_planner_loop` — polls NEW goals → calls `orchestrator.run_plan()` → creates task rows
- `task_executor_loop` — polls READY tasks → runs `agent_runner.run()` — up to 5 concurrent (Semaphore)
- `reclaim_loop` — every 30s, reclaims RUNNING tasks with expired leases back to READY

**Orchestrator** (`orchestrator.py`): Uses the model from `model_config.get_model("orchestrator")` (defaults to `groq/llama-3.3-70b-versatile`). Forced tool call → `PlanSchema` (task DAG JSON). Retries 5x with rate-limit backoff. Handles Groq `tool_use_failed` by salvaging the plan from `failed_generation` in the error response (`_salvage_failed_generation()`). Falls back to `tool_choice="auto"` on attempts 2+. Task IDs are prefixed with `goal.id[:8]_` to avoid UNIQUE constraint collisions. `_rewrite_templates()` rewrites `{{t1.output.field[0]}}` refs to include the prefix.

**Agent runner** (`agent_runner.py`): Generic LLM tool-call loop. Reads agent config via `get_agent_config(name)` (reads live model from `model_config` on every call), calls `acompletion()` in a loop until the agent calls `submit_result`. Idempotency: each tool invocation is hashed into `sha256(task_id:tool:args_json)` and cached in the `tool_calls` table — re-runs return the stored result without re-firing. **The key deliberately excludes `attempt_count`**, because `claim_ready_task` increments it on every claim including the one after a resume, so a key that varied by attempt made a paused task re-fire every write it had already completed (a goal that paused once posted its issue comment twice). That only works alongside the second half: a `WAITING_CREDENTIAL`/`WAITING_WEBHOOK` sentinel is control flow, not a result, so `_execute_tool_idempotent` calls `db.delete_tool_call(ikey)` and returns **before** settling. Cached, a park would replay on the next claim and park the task again forever, whatever the user connects. Both halves or neither — see `test_park_and_resume.py`. Includes: exponential backoff for rate limits, retry-hint injection for Groq `tool_use_failed` errors, `consecutive_errors` counter that forces a "use your knowledge and submit NOW" message after 3 consecutive tool failures, and an early-warning nudge at `max_iter - 3`.

**Agents** (`agent_registry.py`): `researcher` (web_search, http_request, **github_read_file, github_list_dir, github_get_issue, github_search_code, github_get_pr, github_get_pr_files, github_list_prs**, github_list_workflows, github_get_branch_protection, spawn_goal), `writer` (file_ops), `coder` (code_exec, file_ops, web_search, **github_read_file**), `integrator` (every GitHub **write** tool — see the GitHub tools table below — plus **github_read_file, github_list_dir** for confirming which file it is about to change, http_request, wait_webhook, spawn_goal). All go through the same `agent_runner.run()`. Use `get_agent_config(name)` — not `AGENT_REGISTRY[name]` directly — to get the live model setting.

The split is deliberate: `researcher` reads GitHub, `integrator` writes to it. `github_get_pr_files` sits on the researcher because a PR review that has not read the diff is a review of the PR title.

> **There are exactly four executable agents.** `economy.ROLES` lists **six** —
> `orchestrator`, `researcher`, `writer`, `coder`, `integrator`, `notifier` — because it also mints a
> passport for the planner and for a `notifier` that was never built. `notifier` is a **ghost**: it
> holds passport #6 and a reputation row, but it is not in `AGENT_REGISTRY`, has no tools, and can
> never be assigned a task. `ROLES` is left as-is on purpose —
> `seed_passports()` assigns `token_id` from `enumerate(ROLES, start=1)` and `mint_block_for()` from
> `ROLES.index(role)`, so removing an entry would renumber every passport after it and invalidate
> proofs already recorded on chain. Treat the sixth passport as a historical artifact, not a
> capability.

**Model config** (`model_config.py`): Per-role model store. Defaults all roles to `groq/llama-3.3-70b-versatile`. Persists to `backend/model_config.json` (gitignored). `get_model(role)`, `get_all()`, `update(dict)`. Cache invalidated on write. **`AVAILABLE_MODELS` holds 15 ids across 3 providers** — Groq (8: Llama 4 Maverick/Scout, Llama 3.3 70B, Llama 3.2 90B/11B Vision, DeepSeek R1 70B, Qwen QwQ 32B, Gemma 2 9B), Anthropic (5: Opus 4.7, Sonnet 4.6, Haiku 4.5, 3.5 Sonnet, 3.5 Haiku), OpenRouter (2: Llama 3.3 70B, Claude Haiku 4.5). `PUT /api/config/models` **validates against this list and rejects anything else with 400** — an arbitrary LiteLLM string is not accepted, so adding a provider means editing `AVAILABLE_MODELS`, `_FALLBACKS` and `_PROVIDER_KEY_ENV` together.

> There is **no OpenAI, Google/Gemini, Mistral or Mixtral support.** Earlier revisions of this file claimed 40 models across 5 providers; that was never true of this code. `_PROVIDER_KEY_ENV` still lists `openai`/`gemini`/`mistral` prefixes, but no such model id exists, no `Settings` field holds their keys, and `llm.py` never exports their env vars — the entries are vestigial.

**LLM layer** (`llm.py`): `acompletion()` wraps LiteLLM with a fallback chain per model id — one entry in `_FALLBACKS` for each of the 15 ids. At startup `_setenv` exports **three** keys from `config.settings`: `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`. `_is_hard_rate_limit()` catches daily quota (`tpd`, `daily`, `quota`), deprecated-model 404s and overload — any of these mark the model unhealthy for a cooldown (`_hard_limit_cooldown`: 1h for a daily cap, the declared retry-after otherwise, 5min default) and advance to the next candidate. `_is_soft_rate_limit()` catches per-minute throttling and sleeps the declared delay instead of falling back. `has_credentials()` skips any candidate whose provider key is absent, so a keyless provider is never tried.

**OpenRouter last-resort tier**: every chain is post-processed to append `openrouter/meta-llama/llama-3.3-70b-instruct` then `openrouter/anthropic/claude-haiku-4.5`, so a Groq daily cap falls through to OpenRouter rather than failing the goal. Inert without `OPENROUTER_API_KEY` — `has_credentials()` skips the tier entirely.

**Which key paid for a call**: a fallback swaps providers silently, so every successful call emits one JSON line — `logger.info("llm_call %s", …)` with `role`, `requested`, `served_by`, `provider`, `key` (the env var), and `fell_back`. `acompletion()` takes an optional `role=`, threaded from `orchestrator`, `replanner` and both `agent_runner` call sites. Read it in the Render live log:
```
llm_call {"role":"integrator","requested":"groq/llama-3.3-70b-versatile",
          "served_by":"openrouter/meta-llama/llama-3.3-70b-instruct",
          "provider":"openrouter","key":"OPENROUTER_API_KEY","fell_back":true}
```

**Tools** (`tools/`): `TOOL_REGISTRY` in `tools/__init__.py` is the single source of truth — **26 entries, 20 of them GitHub**. The six non-GitHub tools are `web_search`, `http_request` (httpx), `file_ops` (workspace-scoped, path-traversal protected), `code_exec` (subprocess, 30s timeout), `wait_webhook` (suspends the task to `WAITING_WEBHOOK`), `spawn_goal`. The tool surface is GitHub-only; anything not in `TOOL_REGISTRY` is not available to an agent.

> **`web_search` degrades to nothing without a Tavily key.** Order is Tavily → DuckDuckGo *Instant Answer* API → a note telling the model to use its training knowledge. The DDG endpoint is not a web index: for an ordinary developer query (`how to fix a python off by one bug`) it returns `AbstractText: ""` and `RelatedTopics: []`, so the tool yields `{"results": [], "_source": "none"}`. Production currently has **no `TAVILY_API_KEY`**, so web search there is effectively the training-knowledge note.

**GitHub tools** (`tools/github_ops.py`, `tools/github_pr.py`, `tools/github_client.py`):

| Tool | Does | Agent |
|------|------|-------|
| `github_read_file` / `github_list_dir` / `github_search_code` | read repo contents | researcher, coder |
| `github_get_issue` | issue body + comments | researcher |
| `github_get_pr` | PR state, `mergeable_state`, check runs, review verdicts | researcher, integrator |
| `github_get_pr_files` | **the unified diff** — budgeted to 12k chars / 60 files, reports what it truncated | researcher, integrator |
| `github_list_prs` | list PRs | researcher, integrator |
| `github_pr` | commit files to a branch and open a PR (forks when it lacks push access); reports `files_created` vs `files_modified` | integrator |
| `github_merge_pr` | **guarded merge** — see below | integrator |
| `github_review_pr` | formal APPROVE / REQUEST_CHANGES / COMMENT review | integrator |
| `github_request_review` / `github_update_pr` | request reviewers; edit title/body/base/draft/state | integrator |
| `github_create_issue` / `github_close_issue` / `github_add_labels` / `github_post_comment` | issue lifecycle | integrator |
| `github_create_repo` | ship a new project as its own repo | integrator |
| `github_list_workflows` / `github_get_branch_protection` / `github_set_branch_protection` | CI and branch rules | researcher, integrator |

**Merge guard** (`github_merge_pr`): merging is the one GitHub action an agent cannot undo, so it is
gated rather than attempted. It merges only when `mergeable_state` is `clean` or `has_hooks` **and**
no reviewer's latest review is `CHANGES_REQUESTED`. Conflicts, failing or pending checks, unmet
required reviews, `behind`, and draft status each return `ok=False, refused=True` with the specific
blocker (naming the failing check) instead of forcing the merge. `mergeable_state` is computed
asynchronously by GitHub, so `unknown` is polled 6× at 2s rather than treated as a refusal. An
already-merged PR returns `ok=True, already_merged=True` — the `tool_calls` idempotency cache can
replay a merge after a restart, and a replay must not read as a failure. Default method is squash.
The review check is not redundant with `mergeable_state`: on a repo without branch protection, a
`CHANGES_REQUESTED` review leaves the state `clean`.

**Token resolution** (`tools/github_client.py`): one `github_token()` reading `os.environ["GITHUB_TOKEN"]`
first (so `PUT /api/config/keys` takes effect without a restart), then `settings.github_token`. Before
this existed the two files disagreed — `github_pr` read both sources while every tool in `github_ops`
read only `os.environ`, so a token configured the documented way (`backend/.env`, loaded by
pydantic-settings, which never touches `os.environ`) left nine of ten tools parking their task in
`WAITING_CREDENTIAL`. Hosts that inject real env vars, such as Render, hid the split completely.

**Persistence** (`db.py`): SQLite WAL mode, `aiosqlite`. Tables: `goals`, `tasks`, `messages`, `tool_calls`, economy tables `agent_passports`, `agent_reputation`, `proofs`, plus `proof_outbox` (chain submission queue) and `heal_attempts` (self-heal history). Task claim is atomic via `UPDATE ... WHERE id=(SELECT ... LIMIT 1) RETURNING *`. `goals` carries `source`/`heal_depth` (added by migration in `init_db`) so self-heal fix goals are distinguishable and cannot recurse.

> **`attempt_count` is not the retry budget — `tasks.failure_count` is.** `claim_ready_task` bumps
> `attempt_count` on every claim, which is what makes `reclaim_expired_leases` crash-safe, but it
> also bumps on the claim that follows a resume. Checking it against `max_attempts` meant a task
> that parked three times waiting for a credential had no retries left for its first genuine
> failure. `worker.py` now calls `db.record_failure()` in the exception branch only, and compares
> that. Parking is not failing.
>
> For the same reason `find_orphaned_goals` counts `WAITING_WEBHOOK` and `WAITING_CREDENTIAL` as
> **progress**. It used to count them as stalled, and its caller marks such goals `FAILED` with
> "All tasks failed — no progress possible" — so a goal died while its "connect your GitHub"
> prompt was still on screen.

**Economy** (`economy.py` + `api/economy.py`): Simulated Monad agent-economy computed from real task history — deterministic, no RNG. `economy.py` provides canonical hashing (`result_hash`/`tx_hash`/`owner_address`), reputation math (`compute_scores`→composite 0..1000, `badge_for` Gold≥800/Silver≥600/Bronze, `apply_delta_cap` ±20%), and orchestration (`seed_passports` — 6 passports + neutral reputation per role; `recompute_role`; `record_proof` — mints a proof + refreshes reputation, **never raises into the worker**, emits `proof_recorded`/`reputation_update` on the `economy` SSE channel; `backfill`). `worker._after_task_done` calls `economy.record_proof(task, output)`. Seed+backfill run in `main.py` lifespan. Contract addresses come from `chain/registry.py` (`deployments/{chainId}.json`) and are real once deployed. Tests: `test_economy{,_db,_flow,_api}.py`. `scripts/replay_demo.py` mints 3 proofs offline (no LLM keys) for a live demo.

**Chain — real on-chain proof-of-work** (`chain/` + `contracts/` + `chain_worker.py`): Replaces the
simulated tx hashes with a real EVM. `contracts/src/*.sol` (Solidity 0.8.24, self-contained, no
OpenZeppelin) define `AgentPassport` (soulbound, one per agent address), `ProofOfWork` (idempotent —
a duplicate `taskId` **reverts on chain**), `ReputationRegistry` (0..10000, 20% max-delta guard
enforced in bytecode) and `AuditTrail` (events only). `chain/compiler.py` compiles via `solcx`, cached
by source hash. `chain/provider.py` offers two interchangeable backends: `LocalEvmProvider`
(in-process py-evm — real bytecode, tx hashes, receipts and event logs with **no keys, tokens or
network**) and `RpcProvider` (JSON-RPC + local signing, nonce management, EIP-1559, retry).
`chain/client.py` is the only thing the app imports; every method degrades to `None` rather than
raising. Target is chosen by `CHAIN_TARGET` (`local` = 31337 default, `monad-testnet` = 10143) with no
code change. On `local` the contracts redeploy on every boot (`main.py::_init_chain`); deploying to a
real network is an explicit operator action (`scripts/deploy_contracts.py --network monad-testnet`).
`READY` requires **bytecode at every address** (`eth_getCode`), not merely a
`deployments/{chainId}.json` that lists them — binding a contract is local ABI work that
succeeds against any address, so without that check a stale or invented record would make the
UI announce a network nothing is deployed on. Failing to *write* the deployment record is a
warning, never fatal: the contracts are deployed either way.

**Proof outbox** (`chain_worker.py`): `economy.record_proof` mints the local proof instantly and
enqueues to `proof_outbox`; `chain_submit_loop` drains it, submits, and advances
`pending→submitting→confirmed`, with exponential backoff and dead-lettering after 10 attempts. A
chain that is down, slow or undeployed only delays settlement — it never blocks or fails a goal.
Restart-safe: rows stranded in `submitting` are reclaimed on boot. Tests:
`test_contracts.py`, `test_chain_client.py`, `test_chain_pipeline.py`, `test_proof_outbox.py`.

**Verification** (`GET /api/economy/verify/{task_id}`, `scripts/verify_proof.py`): recomputes
`sha256(canonical_json(task.output))` and compares it against `ProofOfWork.getProof`, returning every
intermediate so the check is reproducible by hand. Detects post-hoc tampering of a stored output.
Note: with `CHAIN_TARGET=local` the EVM lives inside the backend process, so the CLI verifies through
the running server's API by default; on a real network it reads the chain directly.

**Self-heal** (`self_heal.py` + `error_classifier.py` + `api/heal.py`): on a goal failure the worker
classifies the error; developer-side bugs fingerprint the error (line numbers, ids, hex and
timestamps normalised away), deduplicate against prior attempts (a bug recurring N times bumps
`recurrence_count` instead of filing N issues), record a `heal_attempts` row, file a GitHub issue —
or record a `simulated` attempt with the issue body it *would* have filed when no `GITHUB_TOKEN` is
set, so the feature demos with zero credentials — and spawn a fix goal tagged `source='self_heal'`,
`heal_depth+1`. `MAX_HEAL_DEPTH=1` means a failing fix goal can never spawn another. Outcomes settle
to `fixed`/`failed` via `settle_outcome` when the fix goal ends. Tests: `test_self_heal.py`,
`test_error_classifier.py`.

### Authentication and delegated authority

**Google says who you are. It does not, and cannot, say what Mergit may do on GitHub or Slack.**
That distinction is the whole design, and getting it wrong is the most common way to misread this
code. A Google token — access, ID or refresh — is only valid at Google. Each third-party provider
is its own authorization server with its own consent, its own client registration and its own
stored token. `include_granted_scopes` unions scopes across *Google's own* services; Google's STS
exchanges credentials *inbound* to Google Cloud only; RFC 8693 is unusable where you are not the
authorization server. The model is **one identity, N separate grants** — never one token reused.

**Identity** (`auth/`): `oidc.py` registers Google through Authlib's discovery document, so the flow
gets `state`, `nonce`, PKCE S256 and full `id_token` validation against Google's JWKS. The flow this
replaced had none of those four and discarded the token it fetched. Users are keyed on the OIDC
`sub`, **never on email** — emails get reassigned inside an organisation, and keying on one would let
a reassigned address inherit the previous holder's stored GitHub and Slack tokens. Scopes stay at
`openid email profile` forever: they are non-sensitive, so no Google verification and no CASA.
Anything more becomes a *connection*, not a login scope.

**Sessions** (`auth/sessions.py`): opaque 32-byte ids backed by a `sessions` row, in a
`__Host-mergit_session` cookie (unprefixed on plain-HTTP dev, because Safari drops `Secure` cookies
on `http://localhost`). Not a JWT: a live session can tell agents to merge into someone's default
branch, so revocation has to be immediate rather than "when it expires". A cookie rather than a
header because `lib/sse.ts` uses `EventSource`, which cannot set headers — and because the SPA is
same-origin, every existing `fetch` carries it with no frontend change.

**Enforcement** (`auth/gate.py`): one middleware scoped to `/api/`, not `Depends()` on ~40 routes —
with thirteen routers, a forgotten dependency is a silently public endpoint, whereas a forgotten
middleware is a route that stops working. It cannot deny-by-default because the SPA is mounted at
`/`, so the fail-closed guarantee lives in **`test_route_coverage.py`**, which walks `app.routes` and
fails the build on any unclassified `/api/` path. CSRF is a synchronizer token in the session row,
handed out only by `GET /api/auth/me`, applied unconditionally — SameSite is defence in depth, not a
control. Origin is compared against `frontend_url` ∪ `cors_origin_list()` and **never against `Host`**,
which is attacker-controlled and would also break the Vite dev proxy's `changeOrigin: true`.

**A session is not an operator.** Three settings are *Mergit's*, not the caller's own — the shared
provider keys (`model_config.json`), the per-role model choice, and the project context whose
`github_repo` is the repository agents act on when a tool call omits one. All three are one file for
the whole deployment, so `require_admin` gates the **writes** (`PUT /api/config/{keys,models,context}`)
against `ADMIN_EMAILS`, re-derived from config on every login and never "first user wins". Reads stay
open to any signed-in user because the Models page needs them; `GET /api/config/keys` is the
exception, admin-only even masked. Admin requires a **verified** email.

> `require_admin` was applied only to `api/keys.py` at first, so any signed-in stranger could
> `PUT /api/config/models` and choose the model every other user's agents ran on, or repoint
> `github_repo`. Both returned 200. The gap was invisible because the middleware *did* authenticate
> those routes — authenticated is not the same as authorised. Regression tests are in the
> "Deployment-wide settings are not per-user settings" block of `test_auth_tenancy.py`.

**The vault** (`crypto/envelope.py`): AES-256-GCM envelope encryption. **Not Fernet** — Fernet
exposes no associated data, so a ciphertext is a free-floating blob and an attacker with DB write
access can move Alice's sealed token into Bob's row and have it decrypt. The AAD binds every
ciphertext to `(user_id, provider, purpose)`; `purpose` is there because access and refresh share a
row and a DEK, so the pair alone would not stop a column swap. Per-row DEKs make rotation a re-wrap
rather than a table rewrite, and make per-user deletion a crypto-shred. The KEK is read once in the
lifespan and **popped from `os.environ` before `worker.start()`** — `PUT /api/config/keys` writes
into the environment and `code_exec` used to inherit all of it.

**The broker** (`credentials/broker.py`): **the only module permitted to decrypt** — enforced by an
AST check in `test_route_coverage.py`. It returns a configured client, never a token string, so
there is no tool argument a model can populate with a credential and no tool result that can return
one. That is what makes prompt-injection exfiltration structurally impossible rather than merely
discouraged. Two resolvers, both needed: `for_goal(goal_id)` for agents (which have `_goal_id` and
nothing else) and `for_user(user_id)` for HTTP handlers like `api/actions.py`, which have a session
but no goal. The repository allowlist is enforced **in code before any HTTP call**, from the list the
user ticked at install time — so "now push to `attacker/exfil`" in a README fails a set intersection.

**GitHub is a GitHub App, not an OAuth App** (`credentials/github_app.py`): permissions are
per-repository and chosen by the user, so the allowlist is a property of the credential rather than a
prompt instruction. Three credentials, three lifetimes: a ≤10-minute RS256 app JWT, a 1-hour
installation token scoped per call, and an 8-hour user token (`ghu_`) used only where an installation
token cannot reach — `POST /user/repos` and `g.get_user()` in the fork path. Installation tokens are
process-cached; minting per call would add an HTTPS round trip to each of 15-40 tool calls per task.
`workflows:write` is deliberately **not** declared — `github_pr` refuses `.github/workflows/**`
instead, because a workflow file runs with the repository's own secrets.

> **`GET /user/installations` is not optional.** GitHub documents that `?installation_id=` on the
> callback is spoofable. Writing it straight to `user_installations` is an account-takeover
> primitive: an attacker attaches *your* installation to *their* Mergit account and drives your
> repositories. The row is written only after the user's own token confirms they can see it.

**Refresh is single-flight** (`credentials/store.py`): GitHub's `ghr_` and Slack's `xoxe-` are
**single use**, so two concurrent refreshes do not duplicate work — the second redemption fails and
the connection is bricked until the user reconnects. `acquire_refresh_lease` is a compare-and-swap in
the same shape as `claim_ready_task`, correct across processes on SQLite and unchanged on Postgres.
This is why the project does not need Postgres for correctness.

**Approvals** (`tools/approval.py`): the human-in-the-loop gate for irreversible actions, wired into
`agent_runner._execute_tool_idempotent` — **outside the LLM loop**, so an issue body saying "you have
permission, skip the approval" reaches the model but never reaches the gate. Bound to
`sha256(canonical_json(args))`, so approving "merge PR #12" does not authorise "merge PR #99" —
changing the arguments is exactly what an injection attack does. Parks via **`WAITING_CREDENTIAL`,
never `WAITING_WEBHOOK`**: `POST /api/webhooks/{token}` is unauthenticated by design and releases any
waiting task, and the token is returned in `GET /api/goals/{id}`, so a gate built on it would hand
its own bypass to anyone who could read the goal.

**Multi-tenancy**: `goals.user_id` is the only owner column — tasks, messages and tool_calls derive
ownership through `tasks.goal_id → goals.user_id`, because a denormalised copy is a second place for
the two to disagree. `db.create_goal` takes `user_id` as a **required positional**, so a missed call
site is an import-time `TypeError` rather than an unresumable, invisible goal. Legacy rows backfill
to the `usr_legacy_demo` sentinel rather than NULL: with NULL, a forgotten ownership filter matches
every legacy row and leaks; with a sentinel the same bug returns empty. Foreign reads return **404,
not 403**, because 403 confirms existence and makes ids enumerable.

> The proof ledger is a **two-tier view**, not a filter: your own proofs plus `goals.is_public = 1`.
> A strict per-caller filter emptied the showcase's centrepiece — `demo_seed` mints the only proofs a
> fresh instance has, so a new user saw an empty ledger beside a non-zero leaderboard computed from
> proofs they could not see.

**Demo seeding** (`demo_seed.py`): with `SEED_DEMO=true`, boot mints a canned goal + 3 proofs when
the ledger is empty, after `_init_chain()` so they verify against the live chain. For hosts with no
persistent disk. Never raises into startup. `scripts/replay_demo.py` is a thin wrapper over the same
module (with pacing) so the two cannot drift. Tests: `test_demo_seed.py`.

**SSE** (`api/stream.py` + `events.py`): In-process `asyncio.Queue` per goal (plus global `economy` and `heal` channels). Worker calls `events.emit()`, stream endpoint drains the queue via Server-Sent Events.

**Interpolation** (`interpolation.py`): Resolves `{{task_id.output.field}}` templates in task inputs before execution. Supports array index access (`{{id.output.key_points[0]}}`) and nested paths (`{{id.output.field[0].subfield}}`). `_resolve_path()` splits on `.` and `[N]` segments.

**API Keys** (`api/keys.py`): `GET/PUT /api/config/keys` — reads/writes credentials to `$RUNTIME_CONFIG_DIR/.env` via `python-dotenv.set_key()` and updates `os.environ` immediately. Returns masked values. `PROVIDER_KEYS` has exactly **five** entries: `groq`, `anthropic`, `openrouter`, `tavily`, `github`. Any other provider name is a 400. A `PUT` also calls `db.resume_credential_tasks(env_var)`, releasing every task parked in `WAITING_CREDENTIAL` for that variable and emitting a `task_update` — this is the seam a future per-tool OAuth "Connect" flow would reuse.

> Frontend note: `Models.tsx` styles only four of them in `PROVIDER_META` (`groq`, `anthropic`, `tavily`, `github`). `openrouter` still renders — the lookup falls back to `{label: provider}` — but unstyled and lowercase. Cosmetic only.

### Frontend (`frontend/`)

Vite + React + TypeScript + Tailwind CSS + Framer Motion + React Flow + SWR.

- `pages/Dashboard.tsx` — goal list + submission input, stats strip, status filters
- `pages/Webhooks.tsx` — GitHub Automation page at `/app/webhooks`; shows webhook URL with copy button, setup guide (ngrok + GitHub settings), and a "Simulate GitHub Issue" form for testing without a real webhook
- `pages/GoalDetail.tsx` — split-pane: task DAG (React Flow) + expandable task panels + live SSE log
- `components/AppNav.tsx` — sticky nav with Dashboard / Models / API Docs links; active-route highlighting
- `pages/Models.tsx` — full-page model config at `/app/models`; Visual tab (per-role cards + custom model input) and JSON tab (raw editor + live validation); API Keys section (all 6 providers, inline key input, saves to `.env` live)
- `pages/Economy.tsx` — Agent Economy hub at `/app/economy`; tabbed Leaderboard / Passports / Proof Ledger, live via `/api/economy/stream`. `pages/AgentDetail.tsx` at `/app/economy/agents/:role` — NFT-style passport + score breakdown + proof history. Components in `components/economy/{Leaderboard,PassportCard,ProofLedger}.tsx`; economy fetchers/types in `lib/api.ts` mirror the backend responses exactly (bare arrays). `ProofLedger` links tx hashes to the active chain's explorer and offers a per-proof **Verify** button showing computed vs on-chain hash
- `pages/SelfHeal.tsx` — Self-Heal timeline at `/app/heal`; stats strip plus every detected bug with classification, recurrence count, linked issue and fix goal
- `components/WalletConnect.tsx` — mock Monad "Connect Wallet" button (deterministic fake 0x address, localStorage-persisted); mounted in `AppNav.tsx`. `ProtectedRoute.tsx` honours `VITE_DEMO_MODE=true` (`frontend/.env`) to bypass Firebase login for demos
- `components/ModelErrorBanner.tsx` — centered modal that appears on goal failure when error is key/quota related; detects provider from error string; inline key input + "Change model" button
- `lib/api.ts` — fetch wrappers for all API endpoints including `getModelConfig`, `updateModelConfig`, `getApiKeys`, `updateApiKey`
- `lib/sse.ts` — `useSSE()` hook — `EventSource` auto-reconnect

In dev, Vite proxies `/api/*` to `:8000`. In production, FastAPI serves `frontend/dist/` at `/`.

### API

All routes under `/api/`. Key endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/goals` | Submit goal → 202. Body is `{"goal": "..."}` — **the field is `goal`, not `goal_text`**; anything else is a 422 |
| GET | `/api/goals` | List goals |
| GET | `/api/goals/{id}` | Full status + tasks + output |
| GET | `/api/goals/{id}/stream` | SSE event stream |
| GET | `/api/config/models` | Get per-role model config |
| PUT | `/api/config/models` | Update per-role model config |
| GET | `/api/config/keys` | Get provider API key status (masked) |
| PUT | `/api/config/keys` | Save provider API key to `.env` + `os.environ` |
| POST | `/api/webhooks/{token}` | Resume WAITING_WEBHOOK task |
| POST | `/api/webhooks/github` | GitHub webhook receiver — auto-creates goals |
| GET | `/api/config/context` | Project context (repo, stack, notes) — note the `/config` prefix |
| PUT | `/api/config/context` | Save project context |
| GET | `/api/config/model-health` | Models currently in cooldown after a hard rate limit |
| GET | `/api/economy/passports` | List 6 agent passports (see the `notifier` note below) |
| GET | `/api/economy/leaderboard` | Ranked reputation (composite + badge) |
| GET | `/api/economy/proofs` | Proof-of-work ledger (newest first) |
| GET | `/api/economy/agents/{role}` | Passport + reputation breakdown + proofs |
| GET | `/api/economy/chain` | The chain the app is actually on (id, name, explorer, addresses) |
| GET | `/api/economy/stream` | Economy SSE stream (`proof_recorded`/`reputation_update`/`proof_*`) |
| GET | `/api/economy/verify/{task_id}` | Verify a stored output against its on-chain proof |
| GET | `/api/economy/chain/status` | Active chain, deployment addresses, outbox depth |
| GET | `/api/heal/attempts` | Self-heal history (deduplicated, newest first) |
| GET | `/api/heal/stats` | Distinct bugs, total recurrences, fixed count |
| GET | `/api/heal/stream` | Self-heal SSE stream |
| GET | `/api/auth/login` | Begin Google sign-in (302 to Google, with state + nonce + PKCE) |
| GET | `/api/auth/callback` | Complete sign-in, mint a session |
| GET | `/api/auth/me` | Current user **and the CSRF token** the SPA echoes on writes |
| POST | `/api/auth/logout` | Revoke the session server-side, then clear the cookie |
| GET | `/api/connections` | What Mergit may do as you, per provider |
| POST | `/api/connections/{provider}/start` | Returns the URL to send the browser to |
| GET | `/api/connections/{provider}/callback` | Complete a connection, resume parked tasks |
| DELETE | `/api/connections/{provider}` | Revoke at the provider, then forget the credential |
| GET | `/api/connections/audit` | Which agent used which connection, for what |
| GET | `/api/approvals` | Irreversible actions waiting on you |
| POST | `/api/approvals/{id}` | Approve or deny; releases the parked task |
| POST | `/api/actions/simulate-issue` | Run the issue-fix pipeline without a real webhook |
| GET | `/api/health` | Health check |

### Environment

Copy `backend/.env.example` to `backend/.env`. The variables that are actually read by code:

| Variable | Read by | Needed for |
|---|---|---|
| `GROQ_API_KEY` | `llm.py` | default model for every role |
| `ANTHROPIC_API_KEY` | `llm.py` | Claude models + first fallback tier |
| `OPENROUTER_API_KEY` | `llm.py` | last-resort fallback tier (see LLM layer) |
| `TAVILY_API_KEY` | `tools/web_search.py` | real web search; without it `web_search` returns nothing useful |
| `GITHUB_TOKEN` | `tools/github_client.py` | every GitHub tool |
| `GITHUB_DEFAULT_REPO` | `tools/github_client.py` | repo when a tool call omits one |

**Production (`mergit.onrender.com`) as of 2026-08-14**, from `GET /api/config/keys`: `GROQ_API_KEY`
set, `OPENROUTER_API_KEY` set, `GITHUB_TOKEN` set (the `Mergit-bot` account), `ANTHROPIC_API_KEY`
**not** set, `TAVILY_API_KEY` **not** set. `OPENROUTER_API_KEY` is a dashboard-only variable — it is
not declared in `render.yaml`, so a blueprint re-sync will not recreate it.

Chain settings (`CHAIN_TARGET`, `CHAIN_RPC_URL`, `CHAIN_PRIVATE_KEY`) default to `local`, which needs
nothing. To use Monad testnet, fund the deployer (free MON: `chainstack.com/monad-faucet` has no gate;
`faucet.monad.xyz` gives 10 MON if the wallet holds ≥0.001 ETH on Ethereum mainnet), then:

```bash
cd backend
.venv/bin/python scripts/deploy_contracts.py --network monad-testnet --dry-run   # check first
.venv/bin/python scripts/deploy_contracts.py --network monad-testnet
```

Model selection is managed at runtime via `backend/model_config.json` (created automatically on first run, gitignored). Edit through the UI "Models" button or directly via `PUT /api/config/models`.

### GitHub Automation (the main demo flow)

`POST /api/webhooks/github` (`api/github_webhook.py`) receives GitHub webhook events and auto-creates goals:
- `issues.opened` → creates goal: "Fix GitHub issue #{n} in {repo}" → orchestrator plans researcher→coder→integrator
- `pull_request.opened` → creates goal: "Review PR #{n} in {repo}" → orchestrator plans researcher→writer→integrator

Standard 3-agent pipeline for issue fixing:
1. **researcher**: `github_list_dir` + `github_read_file` + `github_get_issue` to understand the codebase and bug
2. **coder**: writes the fix using `code_context` from researcher, runs tests via `code_exec`, and reports
   **`path`** — the existing file the fix belongs in (a required output key)
3. **integrator**: `github_pr` (creates PR with fixed files) + `github_post_comment` (posts PR link on original issue)

### Which file the fix lands in

`github_pr` commits whatever path it is handed. A path that does not exist becomes a *new file*
next to the bug, and the PR still opens and still reports `ok: true` — a green run that fixed
nothing. A real run shipped `calculator.py` beside the `calc.py` that had the bug this way.

The filename therefore has to survive every hop, and is defended three times:
1. **Carried** — `coder.output_schema` requires `path`; `agent_runner` rejects a `submit_result`
   without it. The orchestrator threads it on as the integrator's `file_path` input.
2. **Recoverable** — the integrator holds `github_list_dir`, so an integrator handed code and no
   filename can enumerate the repo instead of guessing. Its prompt forbids inventing one.
3. **Visible** — `github_pr` returns `files_created` and `files_modified` on **all three** return
   paths (direct, fork, and the already-open-PR path that `_find_open_pr` returns through). A fix
   meant for an existing file showing up under `files_created` is the failure, stated in the tool
   result. The re-run path matters most: the URL comes back unchanged, so a wrong path there reads
   like a no-op.

### The truncation guard (`_dropped_definitions`)

`files[].content` replaces the **entire** file. An agent that returns only the function it changed
therefore fixes one thing and **deletes the rest of the file** — and the PR still opens green.

This is not hypothetical and it is model-dependent. On `llama-3.3-70b`, the model production runs, a
`stats.py` fix landed as **`+3 −10`**: `spread()` corrected, `median()` and the module docstring
gone. Claude Haiku returned the whole file every time from the identical prompt, which is why earlier
runs never saw it. Prompting does not close this gap.

`_dropped_definitions()` compares top-level `def`/`class` names (regex `_TOP_LEVEL_DEF`, column-zero
only — nested defs are deliberately not matched) in the replacement against the file already at
`base_branch`, and refuses **before any commit**, so a refusal leaves no branch and no partial commit
behind. Missing paths and directories are skipped: a new file has nothing to lose. The error names
what would be lost, because the agent must resend the complete file and "invalid content" would not
tell it that:

```
files[].content replaces the ENTIRE file, and this content would delete code that is
already there — stats.py would lose: median. Read the file, apply your change to it,
and send the complete file back. Do not send only the part you changed.
```

Verified live on the production model: the agent read the refusal, resent the complete file, and the
PR landed `+3 −3` with `median()` intact. Tests:
`test_a_fix_that_would_delete_the_rest_of_the_file_is_refused`,
`test_a_complete_file_with_the_fix_applied_is_committed`,
`test_a_brand_new_file_has_nothing_to_lose`,
`test_renaming_is_not_mistaken_for_deleting_when_the_file_is_whole`.

### The other commit guards

Four sibling checks run in `github_pr()` **before any commit**, cheapest first — the local ones cost
no API call. Each exists because a green PR shipped that fixed nothing:

| guard | refuses | shipped as |
|---|---|---|
| `_empty_contents` | content that is empty or whitespace | PR #30, `+0 −0` |
| `_language_mismatches` | source committed under another language's extension | PR #32, Rust in `auth.py` |
| `_misplaced_new_files` | a NEW file that means one the repo already has | `main/mergesort.py`; PR #34's `merge_sort.py` |
| `_guts_the_file` | a replacement that throws away most of any text file | PR #34's `README.md`, 4 lines → 1 |
| `_dropped_definitions` | replacement content that deletes existing definitions | `stats.py`, `+3 −10` |
| `_changes_nothing` | a diff that changes nothing at all | PR #33, one blank line |

`_language_mismatches` only refuses on an unambiguous verdict: the extension maps to a language the
file shows **no** marker of, while **exactly one** other language shows **two or more** distinct
markers. A stub, a constants file, an unknown extension and a docstring quoting another language all
fall short of that and pass. `.ts` and `.h` are left out of `_EXT_LANG` on purpose — a wrong refusal
costs more than a missed one.

`_misplaced_new_files` compares filenames with case and word separators removed (`_same_file_name`),
so `merge_sort.py`, `MergeSort.py` and `mergesort.py` are one name, and it applies at the repo root
as well as inside subdirectories. Its first version did neither, which is why PR #34 added a second
copy of the algorithm beside the file that had the bug. `calc`/`calculator` stays out of reach — a
different word is not a different spelling.

`_guts_the_file` needs BOTH conditions to fire: the replacement keeps under half the existing
non-blank lines AND is under half its length. Rewriting a document is ordinary work; emptying one is
not, and length is what separates them. Files under four meaningful lines are never policed.

`_changes_nothing` normalises blank lines and trailing whitespace away, so PR #33's 708-bytes-to-707
edit reads as the no-op it is. Only an ALL-nothing request is refused: an unchanged file resent
beside a genuine fix is untidy, not a lie.

### Result validation (`agent_runner`)

A task can end in four places: the `submit_result` tool call, JSON parsed out of a plain assistant
message, the forced final submit after the iteration cap, and JSON parsed out of that message. Only
the first checked anything, so the other three were a way around every guard — that is how PR #32
went out. All four now funnel through `_submission_problem()`, which rejects a non-object result,
missing required keys, and a result that contradicts itself (`_self_reported_failure`: `success:
False`, or an empty required string).

`_wrong_language_for_task` closes the inverse case. `_self_reported_failure` catches an agent that
ADMITS failure; goal `4ad14cf1` showed the worse shape — asked to migrate `auth.py` to **Rust**, the
coder (whose only executor is `code_exec`, a **Python** interpreter, so it cannot run Rust at all)
submitted **Python**, ran it, and set `success: True`. The writer then reported the migration as
done. `_language_mismatches` would have caught it on the commit path, but that goal never reached an
integrator, so the claim is now checked where it is made. `language.requested_language` reads a
target only from a trigger word ("to Rust", "in Python"), so naming the source language in passing
does not confuse it, and `Go` is matched only capitalised or as "golang" — a lowercase "go" after
"to" is the English verb far more often than the language.

`_unrunnable_execution_claim` closes what that exposed. With the language now correct, goal
`b4d3e69a` submitted real Rust at `auth.rs` — and `output: "Login successful"`, a string lifted out
of its own source. `tools/code_exec.py` runs `sys.executable -c`, so there is no toolchain for
anything but Python and that output cannot have come from a run; the Rust did not even compile, its
first line closing a brace with a paren. Being unable to run something is not a failure and is
accepted — an `output` saying it was not executed passes. Saying you ran it when you did not is
refused, because every agent downstream reads that field as evidence the code works.

The forced final gets **one** corrective call with the reason attached, then the task **fails**.
Running out of iterations is a reason to ask again, not a reason to accept anything: handing a
self-declared failure downstream is what produced the empty PR #30 and the broken PR #32. Tests:
`test_forced_final_submit.py`, `test_agent_runner_validation.py`.

### The writer cannot fetch

`_validate_plan` refuses a `writer` task whose inputs are **all** reference keys (`repo`,
`pr_number`, `file_path`, `url`, …). The writer's toolset is `['file_ops']` — given only a pointer to
something it would have to read, it can only invent. It did: goal `efb784fb` ended with a writer
"review" declaring PR #32 "properly tested" without ever having opened it. One real value among the
references is enough to pass. Tests: `test_plan_validation.py`.

PR review: **researcher** (`github_get_pr_files` — the real diff) → **writer** (the review text) →
**integrator** (`github_review_pr` submits it as a review, not a bare comment).

Merge: **integrator** alone — `github_get_pr` then `github_merge_pr`. No researcher, no coder. A
refusal from the guard is a legitimate terminal outcome and is reported as such; the integrator's
prompt forbids retrying it or working around it.

Tests: `test_github_automation.py` covers the wiring (webhook → DAG → dispatch) with GitHub stubbed;
`test_github_tools.py` covers what those stubs stand in for — the merge guard's refusal matrix, diff
truncation, self-review downgrade, PR-creation robustness, and that every tool an agent may call is
actually registered. `scripts/github_e2e.py <owner/repo>` drives all of it against a real repository.

`_validate_plan` in `orchestrator.py` normally refuses a terminal `researcher`/`integrator`, because
raw API data is not the answer a user reads. `_integrator_terminal_is_an_action()` carves out the two
cases where a terminal `integrator` *is* the answer: the issue-fix shape (`coder` and `integrator`
both present), and a direct action on a named PR or issue — detected by a `pr_number`/`issue_number`
input, falling back to a write verb in the task description. The second case was the miss: "merge PR
#3" needs no coder, so the plan was rejected, the orchestrator burned all five attempts, and the goal
failed with a validation error before touching GitHub. The stubbed suite could not see it — it scripts
the plan instead of asking a model for one. Regression tests live in `test_github_tools.py`.

**Local demo setup**: `ngrok http 8000` → copy ngrok URL → GitHub repo Settings → Webhooks → Add webhook. Or use the "Simulate GitHub Issue" form on the Automate page (`/app/webhooks`) to test without a real webhook.
