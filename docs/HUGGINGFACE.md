# Deploying Mergit to Hugging Face Spaces

> ⛔ **Out of date as of 2026-08-13: Docker Spaces now require a PRO subscription.** Only Static
> Spaces remain free, and a static host cannot run this backend. Use **`docs/RENDER.md`** for a
> free deploy with no card. This runbook is kept for reference if you have PRO.

Live in ~20 minutes.

Chosen over Oracle Always Free purely because Oracle's signup needs a card that could not be
verified. If you can complete Oracle signup, **prefer it** — `docs/DEPLOYMENT.md` is the runbook,
and it wins on the one thing this host lacks: a persistent disk. Oracle's arm64 shape builds fine
now that `contracts/out/artifacts.json` is tracked (`compile_all()` returns the cache before it
ever asks solcx for solc, so the x86-only solc download never happens).

**Free CPU tier:** 2 vCPU, 16 GB RAM, ephemeral disk. Measured capacity of this app at a
*tenth* of that CPU: 10 concurrent users, 0 errors, p95 1.3s. Compute is not the constraint.

---

## Before you start: the two things this host changes

**1. The disk is ephemeral.** SQLite and the in-process chain reset on every restart or
rebuild. `SEED_DEMO=true` handles it — on boot with an empty ledger the app mints a canned
goal and three proofs against the chain that is running *now*, so they genuinely verify.
(Committing a populated database would not work: its proofs reference a chain that died with
the process that recorded them, so every Verify button would answer `verified: null`.)

**2. Public Spaces are listed and browsable.** Mergit's API has no authentication —
`POST /api/goals` takes a free-form goal, `code_exec` runs the result in a subprocess, and
`PUT /api/config/keys` rewrites your provider keys. On a discoverable URL that is remote code
execution plus credential theft, and nothing in the app prevents it. Deploy here only with
credentials you are willing to lose.

---

## Steps

### 1. Create the Space

huggingface.co → **New Space**

| Field | Value |
|---|---|
| SDK | **Docker** → Blank |
| Hardware | CPU basic (free) |
| Visibility | **Private** to start |

Start private. Make it public only after step 3 confirms the gate works.

### 2. Add the README frontmatter

Hugging Face reads the Space config from YAML at the very top of `README.md`. Without
`app_port` it looks for port 7860 and the Space never comes up.

```yaml
---
title: Mergit
emoji: 🔗
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 8000
pinned: false
---
```

### 3. Set the secrets

Space → **Settings** → **Variables and secrets**. Add as *secrets*, not variables:

| Name | Value | Why |
|---|---|---|
| `SEED_DEMO` | `true` | Ledger survives the ephemeral disk |
| `GROQ_API_KEY` | your key | Goal execution |
| `MAX_CONCURRENT_TASKS` | `3` | Groq free-tier rate limits bite before CPU does |

Optional, per feature: `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `TAVILY_API_KEY`,
`GITHUB_TOKEN`, `GITHUB_DEFAULT_REPO`.

Never commit these. `backend/.env` is gitignored and must stay that way.

### 4. Push

```bash
git remote add hf https://huggingface.co/spaces/<your-username>/<space-name>
git push hf main
```

Authenticate with an HF access token (Settings → Access Tokens, `write` scope) when prompted
for a password.

### 5. Verify before sharing

Watch the build in the Space's **Logs** tab. Look for `Mergit ready ✓` and
`Chain: ... status=ready`. Then, replacing `<url>` with your Space URL:

```bash
curl -s <url>/api/health
# {"status":"ok","db":"ok","worker":"running","chain":"ready","chain_id":31337}
```

Remember that every route is reachable by anyone who has the URL, including `POST /api/goals` and
`PUT /api/config/keys`.

Then open the URL in a browser, and
`/app/economy` should already show 3 proofs and a populated leaderboard.

### 6. Share

Once the 401 is confirmed, make the Space public if you want a link that works without an HF
account. Give your manager the URL and the password.

---

## Notes

- **Cold start.** The Space sleeps after ~48h idle. Restart takes ~15–30s on 2 vCPU (the 70s
  figure in `ROADMAP.md` was measured at 0.1 CPU).
- **One instance only.** Never raise `--workers`. The worker loops run in the FastAPI
  lifespan, SQLite is a local file and the EVM is in-process; a second worker would race the
  first over a database they cannot share.
- **Verify a *recent* task.** Proofs minted before the current boot have no chain entry on the
  local EVM, so `/api/economy/verify/{id}` returns `verified: null` for them. The seeded ones
  are always current.
- **Load test it yourself:**
  `.venv/bin/python scripts/loadtest.py --base <url> --users 10 --seconds 40`
