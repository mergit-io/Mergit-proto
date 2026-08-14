# Deploying Mergit on Oracle Cloud Always Free

A step-by-step runbook for a permanently free, always-on, single-instance deployment with a
persistent disk and automatic HTTPS.

**Target:** Oracle Cloud Ampere A1 (arm64) · 4 OCPU · 24 GB RAM · Ubuntu 24.04
**Result:** `https://your-domain.com/app`, restart-surviving state, TLS auto-renewed.

---

## Before you start

You need:

- A **credit/debit card** — Oracle uses it for identity verification only. An Always Free account
  cannot accrue charges; it physically cannot provision beyond the free limits unless you
  explicitly upgrade to Pay As You Go.
- A **domain name** you control (Caddy needs it resolving before it can issue a certificate).
- A **Groq API key** at minimum. Everything else is optional.

> ⚠️ **Read the security note in Step 8 before you expose this to the internet.**
> `PUT /api/config/keys` is unauthenticated and writes provider keys to `.env`. Step 8 puts a
> password in front of the whole app, which is the interim fix until real auth lands (M4).

### Why arm64 works

`chain/compiler.py::compile_all()` returns the cached `contracts/out/artifacts.json` whenever its
`source_hash` still matches — **before** it reaches `_ensure_solc()`. solcx maps every Linux to
`solc-bin/linux-amd64` with no CPU-arch check, so on arm64 it would download an x86 binary that
cannot exec. Because `artifacts.json` is tracked, solc is never invoked and the image builds
natively on ARM.

If you edit a `.sol` file, the hash changes and it recompiles — **do that on an x86 machine** and
commit the regenerated `artifacts.json`.

---

## Step 1 — Create the Oracle account

1. Sign up at `cloud.oracle.com` → **Start for free**.
2. Pick your **home region carefully — it cannot be changed.** Choose one geographically near you
   that has Ampere capacity (see Step 2).
3. Complete card verification. Expect a small temporary authorization that drops off.

**Recommended:** once approved, upgrade to **Pay As You Go**. It stays $0 while you remain inside
Always Free limits, and it exempts you from idle-instance reclamation — which matters here,
because Mergit idles at ~0.8% CPU, exactly the profile that policy targets.

## Step 2 — Create the VM

**Compute → Instances → Create instance**

| Field | Value |
|---|---|
| Image | **Ubuntu 24.04** (not Oracle Linux — this guide assumes `apt` and the `ubuntu` user) |
| Shape | **VM.Standard.A1.Flex** — Ampere, arm64 |
| OCPUs / Memory | **4 / 24 GB** (the whole Always Free ARM allowance) |
| Boot volume | 50–100 GB (200 GB total is free) |
| SSH keys | Upload your public key, or let Oracle generate one — **save the private key** |

> 🎲 **"Out of host capacity" is common and not your fault.** Free ARM capacity is genuinely
> scarce in many regions. Options: retry periodically (capacity frees up at odd hours), try a
> different availability domain in the same region, or fall back to two `VM.Standard.E2.1.Micro`
> x86 shapes (1 GB RAM each — enough, since the app uses 250 MB under load, but the image build
> will need swap).

## Step 3 — Open the firewall (both of them)

This is the step everyone loses 30 minutes to. Oracle filters traffic in **two independent
places** and you must open both.

**3a — VCN security list (cloud side):**
Networking → Virtual Cloud Networks → your VCN → Subnet → Security List → **Add Ingress Rules**

| Source CIDR | Protocol | Dest. port |
|---|---|---|
| `0.0.0.0/0` | TCP | 80 |
| `0.0.0.0/0` | TCP | 443 |

**3b — iptables (instance side).** Oracle's Ubuntu images ship with everything except port 22
blocked locally:

```bash
ssh ubuntu@<your-instance-public-ip>

sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save        # survives reboot — do not skip
```

## Step 4 — Point DNS at the box

Create an **A record** for your domain → the instance's public IP.

Verify before continuing — Caddy's certificate request fails if the name doesn't resolve yet:

```bash
dig +short your-domain.com     # must print the instance IP
```

## Step 5 — Install the container runtime

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y podman podman-compose git

# Rootless podman cannot bind ports below 1024 by default; Caddy needs 80 and 443.
echo 'net.ipv4.ip_unprivileged_port_start=80' | sudo tee /etc/sysctl.d/99-podman-ports.conf
sudo sysctl --system
```

## Step 6 — Clone and configure

```bash
git clone https://github.com/mergit-io/Mergit-proto.git
cd Mergit-proto
cp .env.production.example .env.production
nano .env.production
```

Set at minimum:

```env
DOMAIN=your-domain.com
FRONTEND_URL=https://your-domain.com
CORS_ORIGINS=https://your-domain.com
AUTH_SECRET_KEY=<paste output of: openssl rand -hex 32>
GROQ_API_KEY=<your key>
```

Leave `CHAIN_TARGET=local` for the first deploy.

> **What `local` costs you:** the EVM runs inside the app process, so contracts redeploy on every
> boot and proofs minted before a restart stop verifying (`verify` returns `null`). Fine for
> getting live; fix it with a persistent chain — see *Next steps*.

## Step 7 — Build and start

```bash
podman-compose --env-file .env.production up -d --build
```

First build takes 10–20 minutes (npm install, Vite build, Python deps). Then:

```bash
podman-compose --env-file .env.production logs -f mergit
```

## Step 8 — Know what you are exposing 🔒

**Read this before sharing the URL.** The app ships with no authentication of any kind:

- `PUT /api/config/keys` writes provider API keys with no auth.
- `POST /api/goals` is equally open, and the coder agent's `code_exec` tool runs its result in a
  subprocess — so an open URL is **arbitrary code execution in your container**, by design rather
  than by bug. That subprocess shares the process environment, which holds `GITHUB_TOKEN`.
- The frontend ships with `VITE_DEMO_MODE=true`, which bypasses its Firebase login.

Nothing in the application closes this. If the deployment needs to be private, put the protection in
front of it — a Caddy `basic_auth` block on the reverse proxy, an IP allowlist, or a private network —
and keep the container off the public internet. Use a narrowly scoped `GITHUB_TOKEN` regardless.

## Step 9 — Verify

```bash
curl -s https://your-domain.com/api/health
```

Healthy looks like:

```json
{"status":"ok","db":"ok","worker":"running","chain":"ready","chain_id":31337}
```

`"chain":"disabled"` means the contracts did not come up. **The app keeps serving either way, so
the health check alone will not tell you** — read that field explicitly.

Open `https://your-domain.com/app`.

### Prove it carries the load

```bash
podman-compose --env-file .env.production exec mergit \
  python scripts/loadtest.py --base http://localhost:8000 --users 10 --seconds 40
```

Baseline measured on a container throttled to 0.1 CPU / 512 MB: **348 requests, 0 errors, p50
300 ms, p95 1.3 s.** On 4 OCPU / 24 GB this should be far better. If it isn't, something is
misconfigured rather than merely small.

## Step 10 — Survive reboots

```bash
sudo tee /etc/systemd/system/mergit.service >/dev/null <<'EOF'
[Unit]
Description=Mergit
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=ubuntu
WorkingDirectory=/home/ubuntu/Mergit-proto
ExecStart=/usr/bin/podman-compose --env-file .env.production up -d
ExecStop=/usr/bin/podman-compose --env-file .env.production down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload && sudo systemctl enable --now mergit
```

## Step 11 — Back up, offsite

**This is the only step whose absence makes a failure unrecoverable.** Losing `mergit.db` means
losing every goal, task, proof and reputation score.

`deploy/backup-sqlite.sh` uses SQLite's online `.backup()` API, so it takes a consistent snapshot
of a live WAL database — but it writes to `backups/` **on the same machine**. A backup on the box
that dies is not a backup.

```bash
crontab -e
```

```cron
0 3 * * * cd /home/ubuntu/Mergit-proto && COMPOSE="podman-compose" ./deploy/backup-sqlite.sh
30 3 * * * find /home/ubuntu/Mergit-proto/backups -name '*.db' -mtime +14 -delete
```

Then sync `backups/` somewhere else — `rclone` to object storage, or from your laptop:

```bash
rsync -avz ubuntu@<ip>:~/Mergit-proto/backups/ ~/mergit-backups/
```

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| Site unreachable, container Up | Step 3b skipped — local iptables still blocking |
| Caddy cert failure loop | DNS not resolving yet, or port 80 blocked (ACME needs it) |
| `"chain":"disabled"` | Contracts didn't compile/deploy — check `logs mergit` for the reason |
| `curl localhost:8000` → instant HTTP 000 | Podman's pasta binds IPv4 only; use `127.0.0.1:8000` |
| Port 80 permission denied | Step 5 sysctl not applied |
| `exec format error` during build | An x86 binary on arm64 — confirm `artifacts.json` is present and current |
| Build OOM (x86 micro fallback) | 1 GB RAM; add 2 GB swap before building |

## What this deployment deliberately does not do yet

| | Roadmap |
|---|---|
| Real authentication (this uses basic auth as a stopgap) | M4 |
| A chain whose state survives restarts | M2.2 — run `anvil` alongside, add the network to `chain/networks.py`, deploy contracts against it |
| GitHub automation — needs `GITHUB_TOKEN` + a real `GITHUB_DEFAULT_REPO` | M1.1 |

**One instance only, always.** The planner/executor worker starts inside the FastAPI lifespan,
SQLite is a local file, and the EVM is in-process. A second replica means a second worker racing
over a database it cannot share.
