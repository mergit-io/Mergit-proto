"""Ordered, recorded schema migrations.

The previous mechanism was a run of `try: ALTER TABLE …; except: pass` in `init_db`. It
worked for adding a nullable column and nothing else, because a swallowed exception cannot
tell "the column already exists" from "the statement was wrong", and because there was no
record of what had run. Two things the auth work needs are impossible under it:

  * **A backfill.** Migration 003 adds `goals.user_id` and must give every pre-existing row
    an owner. Under try/except-ALTER the backfill would re-run on every boot, which is
    wrong the moment a row legitimately has a different value.
  * **Ordering.** 004 references `users(id)`, so 002 must have run first. A bag of
    independent try/excepts has no order.

Each migration is a name plus a list of statements, applied once inside a transaction and
recorded in `schema_migrations`. Applying is idempotent at the *migration* level rather
than the statement level, which is what makes a backfill safe.

Adding one: append to `MIGRATIONS`. Never edit or reorder an entry that has shipped — a
deployment that already recorded it will not re-run it, so an edit silently applies only
to new installs, which is the worst of both worlds.
"""
import logging

logger = logging.getLogger(__name__)


#: (name, [statements]). Names are permanent identifiers, not descriptions — renaming one
#: makes every existing deployment re-run it.
MIGRATIONS: list[tuple[str, list[str]]] = [
    (
        "001_failure_count",
        [
            # Split the retry budget out of the claim counter. `claim_ready_task` bumps
            # `attempt_count` on every claim including the one after a resume, so parking
            # on a credential used to spend retries.
            "ALTER TABLE tasks ADD COLUMN failure_count INTEGER NOT NULL DEFAULT 0",
            "UPDATE tasks SET failure_count = attempt_count WHERE status = 'FAILED'",
        ],
    ),
    (
        "002_identity",
        [
            # `id` is bound into the AEAD associated data of every credential this user
            # stores, so it is immutable for the life of the row. Regenerating it — an
            # account merge, a provider switch — makes every ciphertext fail to decrypt.
            """CREATE TABLE IF NOT EXISTS users (
                id             TEXT PRIMARY KEY,
                google_sub     TEXT NOT NULL UNIQUE,
                email          TEXT NOT NULL,
                email_verified INTEGER NOT NULL DEFAULT 0,
                name           TEXT,
                picture        TEXT,
                is_admin       INTEGER NOT NULL DEFAULT 0,
                created_at     INTEGER NOT NULL,
                last_seen_at   INTEGER NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
            # Opaque server-side sessions, not JWTs: a live session can command agents that
            # merge pull requests into someone's repository, so revocation has to be
            # immediate rather than "when the token expires".
            """CREATE TABLE IF NOT EXISTS sessions (
                id          TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                csrf_token  TEXT NOT NULL,
                user_agent  TEXT,
                ip_hash     TEXT,
                created_at  INTEGER NOT NULL,
                expires_at  INTEGER NOT NULL,
                revoked_at  INTEGER
            )""",
            "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)",
        ],
    ),
    (
        "003_multitenancy",
        [
            # Two sentinel owners, created before the backfill that references them.
            #
            # Backfilling to a SENTINEL rather than NULL is deliberate. With NULL, a query
            # whose ownership filter someone forgot to add matches every legacy row and
            # leaks them. With a sentinel, the same bug returns an empty set — it fails
            # loudly instead of quietly.
            """INSERT OR IGNORE INTO users
                 (id, google_sub, email, email_verified, name, picture, is_admin,
                  created_at, last_seen_at)
               VALUES ('usr_legacy_demo', 'legacy:demo', 'demo@mergit.local', 0,
                       'Demo (pre-auth)', NULL, 0, 0, 0)""",
            # Owns Mergit's own self-heal goals. Its GitHub identity is
            # settings.mergit_self_heal_token, deliberately outside the per-user broker.
            """INSERT OR IGNORE INTO users
                 (id, google_sub, email, email_verified, name, picture, is_admin,
                  created_at, last_seen_at)
               VALUES ('usr_mergit_system', 'system:mergit', 'system@mergit.local', 0,
                       'Mergit (self-heal)', NULL, 0, 0, 0)""",
            "ALTER TABLE goals ADD COLUMN user_id TEXT REFERENCES users(id)",
            "UPDATE goals SET user_id = 'usr_legacy_demo' WHERE user_id IS NULL",
            # The proof ledger is the showcase's centrepiece. Filtering it strictly to the
            # caller would leave a newly signed-in user staring at an empty page while the
            # leaderboard showed non-zero reputation computed from proofs they cannot see
            # — the product's most visible screen rendering as a bug. Demo-seeded goals are
            # synthetic by construction, so they are marked public and everyone sees them.
            "ALTER TABLE goals ADD COLUMN is_public INTEGER NOT NULL DEFAULT 0",
            "UPDATE goals SET is_public = 1 WHERE user_id = 'usr_legacy_demo'",
            # Pins a webhook-created goal to the installation that fired it, so a goal
            # created while nobody was signed in still resolves to an owner.
            "ALTER TABLE goals ADD COLUMN connection_hint TEXT NOT NULL DEFAULT '{}'",
            "CREATE INDEX IF NOT EXISTS idx_goals_user ON goals(user_id, created_at DESC)",
            # tasks/messages/tool_calls deliberately get NO user_id: ownership derives
            # through tasks.goal_id -> goals.user_id, and a denormalised copy is a second
            # place for the two to disagree.
        ],
    ),
    (
        "004_connections",
        [
            """CREATE TABLE IF NOT EXISTS connections (
                id                  TEXT PRIMARY KEY,
                user_id             TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                provider            TEXT NOT NULL,
                external_account_id TEXT NOT NULL,
                display_name        TEXT NOT NULL DEFAULT '',
                scopes              TEXT NOT NULL DEFAULT '[]',
                status              TEXT NOT NULL DEFAULT 'active',
                installation_id     INTEGER,
                account_type        TEXT,
                alg                 TEXT NOT NULL DEFAULT 'AESGCM-256',
                kek_id              TEXT NOT NULL,
                dek_wrapped         BLOB NOT NULL,
                access_ct           BLOB,
                access_nonce        BLOB,
                refresh_ct          BLOB,
                refresh_nonce       BLOB,
                access_expires_at   INTEGER,
                refresh_expires_at  INTEGER,
                refreshed_at        INTEGER,
                refresh_lock_owner       TEXT,
                refresh_lock_expires_at  INTEGER,
                created_at          INTEGER NOT NULL,
                updated_at          INTEGER NOT NULL,
                revoked_at          INTEGER,
                UNIQUE (user_id, provider, external_account_id)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_conn_lookup ON connections(user_id, provider)",
            """CREATE TABLE IF NOT EXISTS github_installations (
                installation_id      INTEGER PRIMARY KEY,
                account_login        TEXT NOT NULL,
                account_type         TEXT NOT NULL,
                repository_selection TEXT NOT NULL DEFAULT 'selected',
                owner_user_id        TEXT REFERENCES users(id),
                permissions_json     TEXT NOT NULL DEFAULT '{}',
                suspended_at         INTEGER,
                created_at           INTEGER NOT NULL,
                updated_at           INTEGER NOT NULL
            )""",
            # THIS JOIN IS THE AUTHORIZATION CHECK. A row is written only after
            # GET /user/installations confirms the pair — never from the ?installation_id=
            # query parameter, which GitHub's own docs describe as spoofable.
            """CREATE TABLE IF NOT EXISTS user_installations (
                user_id         TEXT    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                installation_id INTEGER NOT NULL,
                verified_at     INTEGER NOT NULL,
                PRIMARY KEY (user_id, installation_id)
            )""",
            # The repository allowlist the user chose at install time, enforced by us in
            # code before any HTTP call — so "now push to attacker/exfil" in a README
            # fails an intersection rather than reaching GitHub.
            """CREATE TABLE IF NOT EXISTS installation_repos (
                installation_id INTEGER NOT NULL,
                full_name       TEXT NOT NULL,
                repo_id         INTEGER,
                PRIMARY KEY (installation_id, full_name)
            )""",
        ],
    ),
    (
        "005_approvals_and_audit",
        [
            """CREATE TABLE IF NOT EXISTS approvals (
                id             TEXT PRIMARY KEY,
                task_id        TEXT NOT NULL,
                goal_id        TEXT NOT NULL,
                user_id        TEXT NOT NULL,
                tool_name      TEXT NOT NULL,
                args_sha256    TEXT NOT NULL,
                summary        TEXT NOT NULL,
                args_json      TEXT NOT NULL,
                credential_key TEXT NOT NULL,
                decision       TEXT,
                decided_by     TEXT,
                decided_at     INTEGER,
                expires_at     INTEGER NOT NULL,
                created_at     INTEGER NOT NULL
            )""",
            # One pending approval per (task, exact arguments). Re-planning with different
            # arguments produces a different hash and therefore a fresh prompt — which is
            # what stops an approved "merge PR #12" being reused for "merge PR #99".
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_approvals_pending
                 ON approvals(task_id, args_sha256) WHERE decision IS NULL""",
            "CREATE INDEX IF NOT EXISTS idx_approvals_user ON approvals(user_id, created_at DESC)",
            # Append-only. The token is never here — only an HMAC fingerprint of it.
            # Written by the broker itself, so completeness is structural: the broker is
            # the only code that can decrypt a credential, so a use that does not appear
            # in this table cannot have happened.
            """CREATE TABLE IF NOT EXISTS credential_uses (
                id              TEXT PRIMARY KEY,
                ts              INTEGER NOT NULL,
                user_id         TEXT NOT NULL,
                agent_role      TEXT NOT NULL DEFAULT '',
                goal_id         TEXT,
                task_id         TEXT,
                connection_id   TEXT,
                provider        TEXT NOT NULL,
                tool_name       TEXT NOT NULL DEFAULT '',
                target          TEXT NOT NULL DEFAULT '',
                scopes_at_call  TEXT NOT NULL DEFAULT '[]',
                token_fp        TEXT NOT NULL DEFAULT '',
                outcome         TEXT NOT NULL DEFAULT 'ok',
                provider_status INTEGER
            )""",
            "CREATE INDEX IF NOT EXISTS idx_cred_uses_user ON credential_uses(user_id, ts DESC)",
            "CREATE INDEX IF NOT EXISTS idx_cred_uses_goal ON credential_uses(goal_id)",
        ],
    ),
    (
        "006_goals_status_index",
        [
            # `claim_new_goal` runs once a second, forever, and without this it is
            # `SCAN goals` + `USE TEMP B-TREE FOR ORDER BY` — a full table scan and a sort
            # of every goal ever created, to find the newest NEW one. The cost grows with
            # the size of the table and goals are never deleted, so it degrades for as
            # long as the deployment lives.
            #
            # With the index the plan becomes
            # `SEARCH goals USING INDEX idx_goals_status (status=?)`, and
            # `find_orphaned_goals` stops scanning too. Nothing in the 1 Hz hot path then
            # scales with database size.
            "CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status, created_at)",
        ],
    ),
]


async def run_migrations(conn) -> list[str]:
    """Apply every unapplied migration in order. Returns the names applied."""
    await conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
             name       TEXT PRIMARY KEY,
             applied_at INTEGER NOT NULL
           )"""
    )
    await conn.commit()

    rows = await (await conn.execute("SELECT name FROM schema_migrations")).fetchall()
    done = {r["name"] for r in rows}

    applied = []
    for name, statements in MIGRATIONS:
        if name in done:
            continue
        for stmt in statements:
            try:
                await conn.execute(stmt)
            except Exception as e:
                # A column added by the OLD try/except-ALTER mechanism already exists on
                # deployments that ran it. That is the one failure that is expected and
                # benign; anything else is a real problem and must not be swallowed, or a
                # half-applied migration gets recorded as complete.
                if "duplicate column name" in str(e).lower():
                    continue
                raise RuntimeError(f"migration {name!r} failed on: {stmt[:80]}…") from e
        import time
        await conn.execute(
            "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
            (name, int(time.time())),
        )
        await conn.commit()
        applied.append(name)
        logger.info("applied migration %s", name)

    return applied
