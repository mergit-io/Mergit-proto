# Deploying Mergit free on Render

`render.yaml` is already in the repo and targets exactly this: Docker runtime, free plan,
health check wired. Deploying is mostly clicking "apply".

> **Why not Hugging Face Spaces?** Docker Spaces now require a PRO subscription — only Static
> Spaces are free, and a static host cannot run this backend. The `docs/HUGGINGFACE.md` runbook
> is kept for reference if you ever have PRO.
>
> **Why not Oracle?** Better host (persistent disk, always on, arm64 builds fine now that
> `contracts/out/artifacts.json` is tracked) — but signup needs a card that verifies. If you can
> get through it, use `docs/DEPLOYMENT.md` instead. This runbook needs no card.

---

## What the free plan costs you

| | Free plan | Consequence |
|---|---|---|
| RAM / CPU | 512 MB / 0.1 CPU | **Fine.** Measured: 10 concurrent users, 0 errors, p95 1.3s, 250 MB used |
| Persistent disk | None | SQLite + chain reset on restart → `SEED_DEMO=true` handles it |
| Idle behaviour | Sleeps after 15 min | **~70s cold start** (measured at 0.1 CPU) → keep it warm, see step 5 |
| Instances | 1 | Correct — never raise this; the worker loops and the EVM live in-process |

---

## Steps

### 1. Push first

Render deploys from GitHub, so anything uncommitted won't ship:

```bash
git add -A && git commit -m "feat: access gate + boot-time demo seeding" && git push
```

### 2. Create the service

render.com → sign up with GitHub (no card for the free plan) → **New** → **Blueprint** →
pick `mergit-io/Mergit-proto`. Render reads `render.yaml` and pre-fills everything.

If Blueprint gives trouble, **New → Web Service** → same repo → Runtime **Docker** →
Plan **Free** → health check path `/api/health` works just as well.

### 3. Set the secrets

Everything marked `sync: false` in `render.yaml` must be filled in the dashboard:

| Key | Value | Notes |
|---|---|---|
| `GROQ_API_KEY` | your key | Needed for goal execution |
| `GITHUB_TOKEN` | a PAT | Needed by all 20 GitHub tools |
| `GITHUB_DEFAULT_REPO` | `owner/repo` | Repo used when a tool call omits one |

`SEED_DEMO=true` and `MAX_CONCURRENT_TASKS=3` are already set in `render.yaml`.
Optional per feature: `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY` (last-resort model fallback),
`TAVILY_API_KEY` (without it `web_search` returns no results).

### 4. Verify the deploy

```bash
curl -s https://<app>.onrender.com/api/health
# {"status":"ok","db":"ok","worker":"running","chain":"ready","chain_id":31337}
```

In the deploy logs, look for `Mergit ready ✓` and `Chain: ... status=ready`. A line reading
`"chain":"disabled"` means the contracts did not come up — the app serves happily either way,
so the health check alone will not tell you.

> ⚠️ **The deployed API is unauthenticated.** `POST /api/goals` is open and the coder agent's
> `code_exec` runs unsandboxed Python in the same process that holds `GITHUB_TOKEN`. Anyone with the
> URL can run code and read that token, so use a scoped token on a repo you don't mind, and treat the
> URL as public.

Then open the URL — `/app/economy` should already show 3 proofs.

### 5. Kill the cold start

Free services sleep after 15 minutes idle, and waking takes ~70s at 0.1 CPU — long enough that
someone clicking your link sees a blank page and assumes it's broken.

Point a free monitor at `https://<app>.onrender.com/api/health` every 10 minutes
(cron-job.org or UptimeRobot, both free, no card). `/api/health` is deliberately outside the
access gate so the ping needs no credentials.

Render's free allowance is 750 instance-hours/month and a month is ~730 hours, so one
always-warm service fits.

---

## Notes

- **Verify a *recent* task.** On the local EVM, proofs minted before the current boot have no
  chain entry, so `/api/economy/verify/{id}` returns `verified: null` for them. The boot-seeded
  ones are always current.
- **Never add `--workers`.** SQLite is a local file and the EVM is in-process; a second worker
  would race the first over state they cannot share.
- **Load test it:** `.venv/bin/python scripts/loadtest.py --base https://<app>.onrender.com --users 10 --seconds 40`
- **Making state durable later:** add a `disk:` block (mount `/data`) and move to the paid
  starter plan. `SEED_DEMO` then becomes a no-op, since it only seeds an empty ledger.
