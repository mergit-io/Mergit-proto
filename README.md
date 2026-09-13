<h1 align="center">Mergit — The AI Agent Economy</h1>

<p align="center">
  <b>Describe the outcome. Not the steps.</b><br>
  Give Mergit one sentence. It plans the work, assigns specialist agents, runs real tools,
  and settles every finished task as a proof on chain.
</p>

<p align="center">
  <a href="https://mergit.onrender.com/app"><img alt="Live demo" src="https://img.shields.io/badge/live%20demo-mergit.onrender.com-6D4AFF?style=flat-square"></a>
  <img alt="Python 3.11" src="https://img.shields.io/badge/python-3.11-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="React 19" src="https://img.shields.io/badge/react-19-149ECA?style=flat-square&logo=react&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/fastapi-async-009688?style=flat-square&logo=fastapi&logoColor=white">
  <img alt="Solidity EVM" src="https://img.shields.io/badge/solidity-EVM-363636?style=flat-square&logo=solidity&logoColor=white">
  <a href="LICENSE"><img alt="MIT licence" src="https://img.shields.io/badge/licence-MIT-blue?style=flat-square"></a>
</p>

<p align="center">
  <img alt="Mergit landing page — a goal decomposed into four agent steps, awaiting settlement" src="docs/assets/landing.png" width="100%">
</p>

## Two-minute demo

**▶ [Watch the demo](https://drive.google.com/file/d/1FcPDda9OeMlVN7rdHWCfaLT2A58aY_VU/view?usp=sharing)** · **[Live app](https://mergit.onrender.com/app)** · **[System and reliability brief](BRIEF.md)**

One sentence in Slack becomes a fix in GitHub, a ticket in Linear, an incident note in
Notion, and an answer in the thread that asked — with every claim checked against the
service that would know.

## The four apps it connects

| App | What Mergit does there | Tools |
|---|---|---|
| **Slack** | Reads the thread a bug is reported in, and replies inside it | 5 |
| **GitHub** | Reads the repository, commits a fix on a branch, opens and updates pull requests, comments on issues | 21 |
| **Linear** | Files the issue, moves it through states, comments the outcome | 6 |
| **Notion** | Writes the incident note the fix is explained in | 4 |

Plus `code_exec`, web search, HTTP and file tools — **42 registered tools** across
**five specialist agents**. Every one of them hits the real API: Slack's `ok: false` on an
HTTP 200 is treated as the failure it is, Linear's `errors[]` likewise.

Credentials resolve through one path per service — the goal owner's stored connection, then
an explicit caller, then a deployment token — and are AES-GCM sealed per user. A test
asserts that the credential broker is the only importer of the unseal function, so **no
tool argument a model can populate ever contains a credential**.

## How reliability was tested

Two things, and the second is the one that matters.

**859 unit tests** cover the orchestrator, the executor, every tool, the credential vault
and each honesty guard.

**`backend/evals/` runs real goals against a live server and grades them by reading the
services back.** Nothing consults a goal's output, its task rows or its tool results —
those are the claims under test, and a harness that graded claims against themselves would
agree with every lie.

Six scenarios against a ~1,000-line service with eight hand-verified defects. Five of the
six are deliberately not the happy path:

| scenario | what it measures | runs | ok | silent |
|---|---|---|---|---|
| `ship_the_fix` | the full four-app chain, on a wrong value | 2 | 2 | 0 |
| `crash_not_logic` | a bug that raises rather than lying | 2 | 2 | 0 |
| `silent_data_loss` | an import that reports success while dropping rows | 2 | 2 | 0 |
| `already_correct` | nothing to fix; a pull request here is the failure | 2 | 2 | 0 |
| `report_only` | a one-step goal must not become a four-step plan | 2 | 2 | 0 |
| `degraded` | an app with no credential; skipped while that app is reachable | — | — | — |

**10/10 · 0% silent failure.**

Two numbers are reported, because one hides the difference that matters:

- **Silent failure** — reported COMPLETED, the services say otherwise, and nothing in the
  run's own output admits it. The dangerous kind: the run nobody goes and checks.
- **Reported shortfall** — missed an objective and *named the one it missed*. There the
  defect is the COMPLETED status, not the honesty.

```bash
cd backend && .venv/bin/python -m evals.run --runs 2
```

### Agents cannot report work they did not do

Every guard below exists because a live run got past the previous ones:

- A result that admits failure, or carries a failed tool envelope, is rejected.
- An invented URL is rejected — addresses are compared against what tools actually returned.
- A claim with no artifact is rejected: "I opened a pull request" with nothing to click does not pass.
- A pull request may not describe code it did not change, or make changes its description does not account for.
- **A pull request may not say it ran something this run never ran.** The deployed demo shipped one saying "Ran the following commands … all outputs are as expected" on a deployment where code execution is unregistered.
- **It may not say the run came back clean when it did not.** The next run got past that a different way: execution returned `ok: false`, and the body still said "All tests passed" — inside a fenced block, where the first check deliberately does not look.
- **A run that read a Slack thread must answer in it**, rather than posting a new message somewhere the reporter is not looking.

## What it does

You write **one sentence**. Everything below follows from it — there is no workflow to define,
no step list to keep current, and no template to fill in.

| | |
|---|---|
| **Plans the work itself** | A planning model turns your sentence into a task graph: every node assigned to an agent, with inputs and dependencies resolved. You never write the steps. |
| **Five specialist agents** | `orchestrator` plans · `researcher` reads repos, threads and issues · `writer` produces prose and diagrams · `coder` writes and runs Python · `integrator` acts on the outside world. |
| **Real tools, real side effects** | 42 tools across four services — 21 GitHub, 5 Slack, 6 Linear, 4 Notion — plus `code_exec` running Python in a subprocess with a 30-second cap, and web search. Not simulated. |
| **Proof of work on chain** | Each finished task is serialised canonically, hashed with SHA-256, and recorded to `ProofOfWork` against the agent's passport. Four deployed Solidity contracts: `AgentPassport`, `ProofOfWork`, `ReputationRegistry`, `AuditTrail`. |
| **Verifiable, not just claimed** | Any proof can be re-checked from the UI: recompute the hash from the stored output, read the chain, compare. Every intermediate value is exposed so a human can redo the check by hand. |
| **Reputation that moves** | Success rate, speed and volume combine into a composite score per agent role, updated as tasks land. |
| **Runs up to five tasks at once** | Independent nodes of the graph execute in parallel, each agent driving its own tool-call loop. |
| **Survives its own failures** | Crash mid-task and it resumes from the same step. A task whose lease expires is reclaimed and retried. Repeated tool calls are hash-matched and served from the stored result. A task that exhausts retries gets replanned. |
| **Agents cannot fake success** | Guards reject a result that admits failure, carries a failed tool envelope, invents a URL, or claims it opened a PR without producing one. |
| **Files its own bugs** | When Mergit hits a bug in itself, it fingerprints it, opens a GitHub issue, and can spawn a goal to fix it. |
| **Live, not polled** | An SSE stream pushes plan, task, tool and proof events to the console as they happen. |

### Two chain targets, one code path

Out of the box the chain runs **inside the app process** (`CHAIN_TARGET=local`, chainId 31337) —
no keys, no tokens, no network, nothing to fund. Point `CHAIN_TARGET` at `monad-testnet`
(chainId 10143) and the same code records the same proofs on a public network.

## Screenshots

**The console** — delegate a goal, watch the swarm, see proofs land.

![Mergit dashboard: goal input, run counters, recent goals and the agent roster](docs/assets/dashboard.png)

**A run** — the task graph the orchestrator drew, each node's agent and state, with the live log alongside.

![Mergit run page: a three-node task graph, researcher to coder to integrator, all done](docs/assets/run.png)

**The proof ledger** — every settled task, its real block and transaction, each one re-checkable.

![Mergit proof ledger: three proofs settled on chainId 31337 at blocks 7, 9 and 11](docs/assets/proof-ledger.png)

> Both screenshots are the local chain (`CHAIN_TARGET=local`) with the demo seed loaded.
> Blocks 7, 9 and 11 are real blocks on the in-process EVM, not placeholders.

## Documentation

| Doc | What it answers |
|---|---|
| **[docs/REPO_MAP.md](docs/REPO_MAP.md)** | **Where everything lives and what owns what** — every module, route, tool, page and script mapped to its job. Start here when you need to find something |
| **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** | **Step-by-step production deploy** on Oracle Cloud Always Free — always-on, persistent disk, automatic HTTPS, $0 |
| **[docs/RENDER.md](docs/RENDER.md)** | **Deploy free with no credit card** on Render — `render.yaml` is already wired; ephemeral disk, seeded on boot |
| **[docs/HUGGINGFACE.md](docs/HUGGINGFACE.md)** | Hugging Face Spaces — reference only; Docker Spaces now require a PRO plan |
| [ARCHITECTURE.md](ARCHITECTURE.md) | How it works: system overview, request lifecycle, GitHub automation pipeline, agent registry, database schema |
| [ROADMAP.md](ROADMAP.md) | What's left: every open issue rated P0–P3, what unblocks it, and the measured hosting analysis |
| [progress.md](progress.md) | What happened: a dated changelog, one block per work session, oldest first |
| [CLAUDE.md](CLAUDE.md) | Working agreements for AI coding agents, plus a condensed architecture summary |

**Design records** live in [`docs/superpowers/`](docs/superpowers/) — a *spec* states a decision and
its rationale, a *plan* carries the ordered steps and their `[x]` state:

- Prototype design — [spec](docs/superpowers/specs/2026-07-18-mergit-prototype-design.md) · [plan](docs/superpowers/plans/2026-07-18-mergit-showcase.md)
- On-chain proof layer — [spec](docs/superpowers/specs/2026-08-12-onchain-proof-layer.md) · [plan](docs/superpowers/plans/2026-08-12-onchain-proof-layer.md)

These are historical: they record what was decided at the time, not necessarily what is true today.
`ARCHITECTURE.md` and `docs/REPO_MAP.md` are the current-state docs.

> ⚠️ [EXPLANATION.md](EXPLANATION.md) is a 5-minute pitch script left over from the hackathon
> framing, and `ROADMAP.md` is still written around demoing rather than shipping. Both need
> rewriting now that this is being built as a real product.

## Setup

Create `backend/.env` from the example and fill in provider/tool keys:

```bash
cd backend
cp .env.example .env
```

Required for normal agent runs:

```env
GROQ_API_KEY=...          # every role defaults to groq/llama-3.3-70b-versatile
```

Optional, with what each one actually buys you:

```env
ANTHROPIC_API_KEY=...     # Claude models, and the first fallback tier
OPENROUTER_API_KEY=...    # last-resort fallback once Groq's daily cap is hit
TAVILY_API_KEY=...        # real web search — see the warning below
GITHUB_TOKEN=...          # required by all 20 GitHub tools
GITHUB_DEFAULT_REPO=owner/repo
```

> **Without `TAVILY_API_KEY`, `web_search` returns nothing usable.** The fallback is the DuckDuckGo
> *Instant Answer* API, which is not a web index — an ordinary developer query comes back with an
> empty abstract and no related topics, so the tool hands the model a "use your training knowledge"
> note instead of results.

## Test Locally

```bash
./scripts/test-local.sh
```

This installs backend/frontend dependencies, compiles backend Python files, and builds the frontend.

## Development

Terminal 1:

```bash
cd backend
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Terminal 2:

```bash
cd frontend
npm run dev
```

Open `http://localhost:3000/app`.

## Production

### Render

Use Render for the managed cloud deployment. The repo includes `render.yaml`, so Render can create the web service, Docker build, health check, and persistent disk from the Blueprint.

1. Push this repo to GitHub.
2. In Render, create a new Blueprint from the repo.
3. Use the generated `mergit` web service.
4. Set these environment variables in Render:

```env
FRONTEND_URL=https://your-render-or-custom-domain
CORS_ORIGINS=https://your-render-or-custom-domain
GROQ_API_KEY=...
GITHUB_TOKEN=...
GITHUB_DEFAULT_REPO=owner/repo
```

Optional:

```env
ANTHROPIC_API_KEY=...
OPENROUTER_API_KEY=...
TAVILY_API_KEY=...
```

> ⚠️ **The deployed API is unauthenticated.** `POST /api/goals` is open and the coder agent's
> `code_exec` runs unsandboxed Python in the same process that holds `GITHUB_TOKEN`, so anyone with
> the URL can run code and read that token. This is a deliberate showcase trade-off — don't point a
> deployment at a repo or a token you care about.

Open:

```text
https://your-render-or-custom-domain/app
```

**On Render's free plan there is no persistent disk.** `render.yaml` sets `plan: free` and declares no
`disk:` block, so `/data` is ephemeral: `/data/mergit.db`, `/data/workspace` and `/data/config` are
wiped on every restart and re-seeded by `SEED_DEMO=true`. For durable state, add a `disk:` block and
move to `plan: starter`.

Run one instance only. The planner/executor worker starts inside the FastAPI lifespan, so multiple app instances would start multiple internal workers.

### One container, no proxy

The fastest way to see the production image work — useful before you point a domain at anything. Works the same with `docker` in place of `podman`:

```bash
podman build -t mergit:local -f Dockerfile .
podman run -d --name mergit -p 8000:8000 \
  -e GROQ_API_KEY="$GROQ_API_KEY" \
  -v mergit_data:/data \
  mergit:local

curl -s localhost:8000/api/health
```

A healthy response reports the chain the container actually brought up:

```json
{"status":"ok","db":"ok","worker":"running","chain":"ready","chain_id":31337}
```

`"chain":"disabled"` there means the contracts did not compile in the image — the app keeps serving, so the health check alone would not tell you.

### Docker / Podman Compose

Use this if you deploy to your own VPS instead of Render. Every `docker compose` command below works as `podman-compose` (or `podman compose`) unchanged.

The production deployment is a Docker Compose stack:

- `mergit`: one FastAPI process that serves the built frontend and runs the internal planner/executor worker.
- `caddy`: HTTPS reverse proxy with automatic TLS certificates.
- `mergit_data`: persistent volume for SQLite and agent workspace files.

```bash
cp .env.production.example .env.production
```

Edit `.env.production` and set:

```env
DOMAIN=your-domain.com
FRONTEND_URL=https://your-domain.com
CORS_ORIGINS=https://your-domain.com
AUTH_SECRET_KEY=replace-with-a-long-random-secret
GROQ_API_KEY=...
ANTHROPIC_API_KEY=...
TAVILY_API_KEY=...
```

Point your domain's `A` record at the server, then start the stack:

```bash
docker compose --env-file .env.production up -d --build
```

Open `https://your-domain.com/app`.

Check health and logs:

```bash
curl https://your-domain.com/api/health
docker compose --env-file .env.production logs -f mergit
```

Create a SQLite backup from the running container:

```bash
./deploy/backup-sqlite.sh
```

Run one app container and one uvicorn worker for now. The planner/executor worker starts inside the FastAPI lifespan, so multiple app replicas would start multiple internal workers. The production container stores state at `/data/mergit.db`, `/data/workspace`, and `/data/config`.
