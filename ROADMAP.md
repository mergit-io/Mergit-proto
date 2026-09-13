# Mergit — Roadmap & Issue Register

**Last verified:** 2026-08-13, against the live DB, the running container, and `git` — not from memory.

**Where the build actually stands:** 170 tests passing · 23 goals COMPLETED / 67 tasks DONE ·
68 proofs minted, 14 confirmed on chain · 2 self-heal attempts recorded · load-tested at
10 concurrent users with 0 errors.

The core engine works and has been proven by running it. Everything below is either *ship
plumbing*, *a feature that has never been given its credential*, or *a hole that only shows up
under failure*.

---

## How to read the severity ratings

| | Meaning | Rule of thumb |
|---|---|---|
| **P0** | Blocks the demo, or the product tells a viewer something untrue | Fix before anyone else sees it |
| **P1** | Blocks the next milestone, or a headline feature has never actually run | Fix this week |
| **P2** | Real hole, but only under failure or edge conditions | Fix before it bites in front of someone |
| **P3** | Deferred by choice — known gap, not a surprise | Schedule it, don't rush it |

A thing being **broken** and a thing being **blocked** are different, and the register keeps them
apart. Most of what's outstanding is blocked on a credential or an account, not on code.

---

## M0 — Get it in front of the manager · **P0** · ~2 hours

The only milestone with a deadline attached to a person. Everything here is plumbing; none of it
is hard, and all of it is required.

| # | Item | Status | Why it matters |
|---|---|---|---|
| 0.1 | 2 commits unpushed (`9fd29a1`, `225b7bd`) | ✅ | Pushed in `b56eaa9`. Both are the chain-honesty fixes — a host pulling from GitHub would have deployed the *old, lying* build |
| 0.2 | `git remote` renamed `mergit-proto` → `Mergit-proto` | ✅ | Remote now `git@github.com:mergit-io/Mergit-proto.git` |
| 0.3 | `backend/scripts/loadtest.py` untracked | ✅ | Tracked. It's the evidence for the 10-user claim; untracked evidence is an anecdote |
| 0.4 | Pick a host + deploy | 🔶 | **Render free** — `render.yaml` was already wired for it. Runbook: `docs/RENDER.md`. Oracle deferred (card verification kept failing), HF ruled out (Docker Spaces now need PRO). Revisit Oracle/AWS only when scaling |
| 0.5 | Seed-on-boot (`SEED_DEMO=true`) | ✅ | `demo_seed.py`. Verified live: seeded proofs return `verified: true` against the running chain |
| 0.7 | **Access gate for the public URL** (`ACCESS_PASSWORD`) | ✅ | `access_gate.py` — see the P0 note under M4. Verified live: 401 without credentials, 200 with |
| 0.6 | A stray SQLite db under `frontend/` is tracked — 68 KB, empty schema, pre-rebrand leftover from `e0f6b36` | ⬜ | Scanned clean (no credentials, all tables empty). `git rm --cached` it — gitignore does not untrack what is already tracked |

> **SQLite files must never be tracked.** `.gitignore` previously anchored the rule to
> `backend/mergit.db`, so any tool run from a different cwd left a stray `mergit.db` that git
> offered to commit — `sqlite3.connect()` *creates* the file when it is missing. The stray db under
> `frontend/` got into the repo exactly that way. The rule is now unanchored (`*.db`, `-wal`, `-shm`, `-journal`).
> Committing a live DB would be worse than useless anyway: its proofs reference a chain that died
> with the process that made them, so every Verify button would return `verified: null`. That is
> what 0.5 exists for — regenerate the data, don't ship it.

### Hosting — measured, not estimated

Load test on a container throttled to free-tier scale (`--cpus 0.1 --memory 512m`), 10 concurrent
users each holding an SSE stream open while polling all 6 dashboard endpoints every 5s:

> **348 requests, 0 errors.** p50 300ms · p95 1.3s · 250 MB of 512 MB RAM used.
> Unthrottled, the same test gives p95 265ms.

**10 concurrent users is not the constraint. Four other things are:**

1. **Exactly one instance, always.** The worker loops run inside the FastAPI lifespan, SQLite is a
   local file, and the EVM is in-process. Two replicas = two planners racing over one DB they
   cannot share. No autoscaling, no `--workers 2`.
2. **70-second cold start** (chain deploys during it). Any host that sleeps on idle — Render Free
   sleeps at 15 min — means the manager clicks the link and watches a blank page for over a minute.
   Mitigated by a free cron pinging `/api/health` every 10 min.
3. **No persistent disk on most free tiers** → SQLite *and* the chain reset on every redeploy.
   That's what item 0.5 exists for.
4. **The real ceiling is Groq's free rate limit, not the host.** Ten people *browsing* is fine. Ten
   people *submitting goals at once* is ~30–50 LLM calls and free-tier RPM/TPM throttles bite long
   before 0.1 CPU does. Set `MAX_CONCURRENT_TASKS=3` on a free tier.

| Host | Fits? | Catch |
|---|---|---|
| **Oracle Always Free — x86 micro** | Always on, persistent disk; `compose.yaml` + `deploy/Caddyfile` already target exactly this | Card for ID check; you operate the box |
| **Hugging Face Spaces (Docker)** | 2 vCPU / 16 GB, no card, public URL in minutes | Ephemeral disk; must listen on 7860; sleeps after 48h idle |
| **Render Free** | `render.yaml` already in repo — lowest effort | 15-min sleep + 70s cold start; no disk |
| **Koyeb Free** | Always-on nano, no sleep | Ephemeral disk; one service |

> ⚠️ **Oracle's ARM tier will not build this image.** `solcx/install.py::_get_os_name()` maps every
> Linux to one target and downloads `solc-bin/linux-amd64` with no CPU-arch check — on ARM64 it
> fetches an x86 ELF that cannot exec, and `backend/contracts/out/` is gitignored so a clean clone
> has no cached artifact to fall back on. Use the **x86** shape, or commit the compiled artifacts.

Free-tier terms change constantly — verify current limits before committing an afternoon.

---

## M1 — Turn on the features that have never run · **P1** · ~1 hour + accounts

Every item here is **blocked on a credential, not on code**. The code paths are written and
unit-tested; none has ever executed against the real service. That distinction matters when
someone asks "does it work?" — the honest answer today is "it has never been tried."

| # | Item | Blocker | Fix |
|---|---|---|---|
| 1.1 | **GitHub automation — the headline demo** | no `GITHUB_TOKEN`; `GITHUB_DEFAULT_REPO` is literally the string `owner/repo` | Set both in `backend/.env`, then use the **Simulate GitHub Issue** form on `/app/webhooks` — no ngrok needed |
| 1.2 | `web_search` | no `TAVILY_API_KEY` | Set it, or accept the DuckDuckGo → training-knowledge fallback (works, weaker) |
| 1.3 | Slack notify | no `SLACK_WEBHOOK_URL` | Set it |
| 1.4 | Orchestrator constraint fix | covered by a unit test, never re-confirmed on a live model run | Submit a goal with an explicit constraint ("under 200 words") and check the terminal task restates it |

**1.1 is the single highest-value item in this document.** `CLAUDE.md` calls the
researcher→coder→integrator pipeline "the main demo flow," and it is the one thing a manager will
find most impressive — an agent that reads a real issue, writes a real fix, and opens a real PR.
It is also the least proven. One token turns the largest untested surface in the codebase into the
strongest thing in the demo.

There is live evidence it stalls exactly here: goal `b3e2ba89` sits RUNNING with task
`b3e2ba89_t2` (integrator) in `WAITING_CREDENTIAL` — the system correctly detected the missing
GitHub token and suspended rather than failing. That's the design working. It's also a goal that
can never finish until 1.1 is done.

---

## M2 — Make the chain durable · **P1** · ~1 hour (anvil) or blocked (Monad)

### 2.1 · Monad testnet — **blocked, not broken** · P2
Every faucet (official, Alchemy, Chainstack, QuickNode) gates on an Ethereum **mainnet** ETH
balance, 0.001–0.08 ETH depending on the site. No MON was ever obtained, so the contracts have
never touched a public network.
- **Real fix:** ~0.005 ETH in a wallet → `faucet.monad.xyz` → set a real 32-byte
  `CHAIN_PRIVATE_KEY` → `scripts/deploy_contracts.py --network monad-testnet --dry-run`, then live.
- ⚠️ The wallet `0x5eDABc9F74C90a9AE729e186fA051522f79cB144` was typed into a third-party faucet
  site and is **burned** — testnet only, never give it real value.

### 2.2 · **Run `anvil` instead — 90% of the value, zero faucet** · P1 · *recommended*
Point `CHAIN_TARGET`/`CHAIN_RPC_URL` at a local `anvil` or Hardhat node on the deploy box. Real
RPC, real tx hashes, **survives app restarts** — and the code path is byte-for-byte the one Monad
would use, so 2.1 later becomes a config change. This also fixes 2.4.

### 2.3 · `CHAIN_PRIVATE_KEY` in `.env` is 42 chars — that's an **address**, not a key · P2
Harmless while `CHAIN_TARGET=local` (the in-process EVM ignores it). Fails instantly on any real
network, including anvil with a funded account. Replace with a 66-char key when 2.1 or 2.2 lands.

### 2.4 · 54 of 68 proofs have no chain entry · P2
By design — the local EVM dies with the process, so `/api/economy/verify/{id}` returns
`verified: null` for anything minted before the current boot. Only the 14 outbox-confirmed proofs
verify. **For a demo, verify a recent task or re-run `scripts/replay_demo.py` first.** Permanently
fixed by 2.2.

### ✅ 2.5 · `deployments/10143.json` with invented addresses — **FIXED & VERIFIED**
Deleted; only `31337.json` remains. `ChainClient` now requires bytecode at every address
(`eth_getCode`, `backend/chain/client.py:57`) before reporting READY — binding an ABI succeeds
against *any* address, so without that check the UI would have announced "Live on Monad Testnet"
while every call silently returned nothing. Test at `backend/test_chain_client.py:41`.

---

## M3 — Close the reliability holes · **P2** · ~1 hour

### 3.1 · Goals that crash during PLANNING are stranded forever · P2 · *~10 lines*
`find_orphaned_goals` (`backend/db.py:494`) requires `g.terminal_task_id IS NOT NULL`, so a goal
that died between "picked up by the planner" and "first task row written" is invisible to the
reclaim loop — permanently.

**Live proof:** goal `f3e6b093` ("Wire the ledger into the live SSE stream") has been PLANNING with
zero task rows since before the reboot. It will never move again.

**Fix:** add a second branch — goals in PLANNING, with zero task rows, past an age threshold, go
back to NEW so the planner retries. `db.py` + `worker.py`. Write the test RED first: insert a
PLANNING goal with no tasks, assert the reclaim loop returns it.

### 3.2 · `WAITING_CREDENTIAL` is invisible in the UI · P2
Goal `b3e2ba89` is parked waiting on `GITHUB_TOKEN` and the dashboard gives no hint that a human
supplying one credential would unblock it. The state exists in the DB and the resume path
(`resume_credential_tasks`) is written — it just isn't surfaced. A banner naming the missing
variable, linked to the keys page, closes the loop.

---

## M4 — Real authentication · **P3** · deferred by choice

The frontend is built with `VITE_DEMO_MODE=true`, which bypasses Firebase login entirely. Correct
for a manager demo — wrong for anything public.

**Fix:** rebuild with `--build-arg VITE_DEMO_MODE=false` and set the 6 `OAUTH_*` vars. Do this
before the URL goes anywhere beyond the demo, because the app currently writes provider API keys to
`.env` from an unauthenticated UI endpoint (`PUT /api/config/keys`).

> 🔒 **This rating was wrong, and M0.7 now covers the urgent half of it.** The original note said an
> unlisted URL made this an acceptable trade-off. That understated it: the API is unauthenticated
> end to end, so anyone who finds the URL can not only read and overwrite the provider keys but
> submit a goal that reaches the coder agent's `code_exec` — arbitrary Python in a subprocess. On a
> *listed* host (Hugging Face publishes public Spaces in a browsable directory) that is P0, not P3.
>
> `ACCESS_PASSWORD` (M0.7) closes it: HTTP Basic over everything except `/api/health`. What remains
> at P3 here is genuine multi-user auth — per-user identity and sessions — which a single shared
> secret does not provide and a demo does not need.

---

## M5 — Real wallet connection · **P3** · you already deferred this

`WalletConnect.tsx` generates a deterministic fake `0x` address into localStorage. Real fix is
wagmi + a WalletConnect project ID. Only worth doing after M2 — a real wallet against a chain
that dies on restart is a worse demo than an honest mock.

---

## M6 — Browser automation (Playwright) · **P3** · never started

Floated as an idea, no code written. Real value is end-to-end tests that drive the actual UI, which
would have caught the "UI announces the wrong chain" class of bug that M2.5 fixed in the backend.
Worth scoping only once M0–M3 are done.

---

## Suggested order

```
M0 (0.1→0.3, 15 min)  →  M0 (0.4→0.5, host)  →  M1.1 (GitHub token)  →  M3.1  →  M2.2 (anvil)  →  M1.2–1.4  →  M3.2  →  M4  →  M5  →  M6
```

**The reasoning:** M0.1–0.3 is fifteen minutes and stops the wrong build shipping. Host choice is
yours and gates everything visible. M1.1 is one token that converts the largest untested surface
into the strongest demo moment. M3.1 is ten lines and removes a whole class of permanent stall.
M2.2 makes every proof verifiable forever, which is the claim the entire economy layer rests on.

**Two decisions are yours and block work:** which host (M0.4), and whether a GitHub token is
available for the account you want PRs raised against (M1.1).
