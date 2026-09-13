"""Reading and writing the `connections` table.

Split from `broker.py` so the boundary stays visible: this module knows about rows and
ciphertext, the broker knows about tools and audit. Both are inside `credentials/`, which
is the only package permitted to import `crypto.envelope.unseal`.

The single-flight refresh lease at the bottom is the load-bearing piece. GitHub's `ghr_`
and Slack's `xoxe-` refresh tokens are **single use**: redeeming one invalidates it and
the access token it came with. Two workers refreshing the same connection concurrently
therefore do not merely duplicate work — the second redemption fails and the connection is
permanently bricked, requiring the user to reconnect. The lease is a compare-and-swap in
the same shape as `claim_ready_task`, which means it is correct across processes on SQLite
(WAL serialises writers) and ports to Postgres unchanged. That is the reason this project
does not need Postgres for correctness.
"""
import json
import logging
import time
import uuid

import db
from crypto import envelope

logger = logging.getLogger(__name__)


class NoConnection(Exception):
    """Raised when a tool needs a credential the user has not granted.

    Carries what the UI needs to fix it: which provider, and where to go. `github_client`
    turns this into the `WAITING_CREDENTIAL` sentinel, which parks the task rather than
    failing the goal — the user connects, and the same run continues.
    """

    def __init__(self, provider: str, user_id: str, reason: str = ""):
        self.provider = provider
        self.user_id = user_id
        self.reason = reason
        super().__init__(reason or f"no active {provider} connection for {user_id}")

    @property
    def credential_key(self) -> str:
        """The key `db.resume_credential_tasks` will be called with when it is granted.

        Per-user, unlike the old env-var names. `resume_credential_tasks("GITHUB_TOKEN")`
        released *every* task in the system waiting on that variable, so with per-user
        credentials one person connecting would have resumed everybody's parked tasks.
        """
        return f"conn:{self.provider}:{self.user_id}"

    @property
    def connect_url(self) -> str:
        return f"/app/connections?connect={self.provider}"


def _now() -> int:
    return int(time.time())


async def upsert_connection(
    *,
    user_id: str,
    provider: str,
    external_account_id: str,
    access_token: str,
    refresh_token: str = "",
    display_name: str = "",
    scopes: list[str] | None = None,
    installation_id: int | None = None,
    account_type: str = "",
    access_expires_at: int | None = None,
    refresh_expires_at: int | None = None,
    status: str = "active",
) -> str:
    """Seal a credential and store it. Returns the connection id.

    A fresh DEK per write, not per row: re-connecting rotates the data key as a side
    effect, so a DEK that leaked with an old backup does not open the new tokens.
    """
    kek_id, dek, wrapped = envelope.new_dek()
    access_ct, access_nonce = envelope.seal(
        dek, access_token, user_id=user_id, provider=provider, purpose="access")
    refresh_ct, refresh_nonce = envelope.seal(
        dek, refresh_token, user_id=user_id, provider=provider, purpose="refresh")

    now = _now()
    async with db.get_conn() as conn:
        row = await (
            await conn.execute(
                """SELECT id FROM connections
                   WHERE user_id=? AND provider=? AND external_account_id=?""",
                (user_id, provider, external_account_id),
            )
        ).fetchone()
        conn_id = row["id"] if row else f"con_{uuid.uuid4().hex[:26]}"

        await conn.execute(
            """INSERT INTO connections
                 (id, user_id, provider, external_account_id, display_name, scopes, status,
                  installation_id, account_type, alg, kek_id, dek_wrapped,
                  access_ct, access_nonce, refresh_ct, refresh_nonce,
                  access_expires_at, refresh_expires_at, refreshed_at,
                  created_at, updated_at, revoked_at)
               VALUES (?,?,?,?,?,?,?,?,?,'AESGCM-256',?,?,?,?,?,?,?,?,?,?,?,NULL)
               ON CONFLICT(user_id, provider, external_account_id) DO UPDATE SET
                 display_name=excluded.display_name,
                 scopes=excluded.scopes,
                 status=excluded.status,
                 installation_id=excluded.installation_id,
                 account_type=excluded.account_type,
                 kek_id=excluded.kek_id,
                 dek_wrapped=excluded.dek_wrapped,
                 access_ct=excluded.access_ct,
                 access_nonce=excluded.access_nonce,
                 refresh_ct=excluded.refresh_ct,
                 refresh_nonce=excluded.refresh_nonce,
                 access_expires_at=excluded.access_expires_at,
                 refresh_expires_at=excluded.refresh_expires_at,
                 refreshed_at=excluded.refreshed_at,
                 updated_at=excluded.updated_at,
                 revoked_at=NULL""",
            (conn_id, user_id, provider, external_account_id, display_name,
             json.dumps(scopes or []), status, installation_id, account_type,
             kek_id, wrapped, access_ct, access_nonce, refresh_ct, refresh_nonce,
             access_expires_at, refresh_expires_at, now, now, now),
        )
        await conn.commit()
    logger.info("stored %s connection for user=%s account=%s", provider, user_id,
                external_account_id)
    return conn_id


async def get_connection(user_id: str, provider: str) -> dict | None:
    """The user's active connection for a provider, with ciphertext still sealed."""
    async with db.get_conn() as conn:
        row = await (
            await conn.execute(
                """SELECT * FROM connections
                   WHERE user_id=? AND provider=? AND revoked_at IS NULL
                   ORDER BY updated_at DESC LIMIT 1""",
                (user_id, provider),
            )
        ).fetchone()
    return dict(row) if row else None


async def list_connections(user_id: str) -> list[dict]:
    """Everything this user has connected — for the Connections page.

    Returns metadata only. No ciphertext, no token, not even a masked one: a masked
    provider key is a reasonable UI for *Mergit's* own keys, and the wrong idea entirely
    for a credential Mergit holds on someone's behalf. There is nothing for the user to
    copy, so there is nothing to show.
    """
    async with db.get_conn() as conn:
        rows = await (
            await conn.execute(
                """SELECT id, provider, external_account_id, display_name, scopes, status,
                          installation_id, account_type, created_at, updated_at,
                          access_expires_at
                   FROM connections WHERE user_id=? AND revoked_at IS NULL
                   ORDER BY provider""",
                (user_id,),
            )
        ).fetchall()
    return [
        {
            "id": r["id"],
            "provider": r["provider"],
            "account": r["external_account_id"],
            "display_name": r["display_name"],
            "scopes": json.loads(r["scopes"] or "[]"),
            "status": r["status"],
            "installation_id": r["installation_id"],
            "account_type": r["account_type"],
            "connected_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


def open_secrets(row: dict) -> tuple[str, str]:
    """Decrypt (access, refresh) from a connection row.

    Only ever called from inside `credentials/`. The AAD is reconstructed from the row's
    own columns, so a row whose `user_id` was tampered with fails to decrypt.
    """
    dek = envelope.unwrap_dek(row["kek_id"], row["dek_wrapped"])
    access = envelope.unseal(
        dek, row["access_ct"], row["access_nonce"],
        user_id=row["user_id"], provider=row["provider"], purpose="access")
    refresh = envelope.unseal(
        dek, row["refresh_ct"], row["refresh_nonce"],
        user_id=row["user_id"], provider=row["provider"], purpose="refresh")
    return access, refresh


async def mark_status(connection_id: str, status: str) -> None:
    """Move a connection between active / needs_reauth / revoked / pending_org_approval."""
    async with db.get_conn() as conn:
        await conn.execute(
            "UPDATE connections SET status=?, updated_at=? WHERE id=?",
            (status, _now(), connection_id),
        )
        await conn.commit()


async def revoke_connection(user_id: str, provider: str) -> int:
    """Forget a connection. Returns rows affected.

    The caller must revoke at the provider *first*. Deleting our copy before telling
    GitHub or Slack destroys the only handle we had on a token that is still live under
    Mergit's client id — the user believes they disconnected and nothing was withdrawn.
    """
    async with db.get_conn() as conn:
        cur = await conn.execute(
            "UPDATE connections SET revoked_at=?, status='revoked', updated_at=? "
            "WHERE user_id=? AND provider=? AND revoked_at IS NULL",
            (_now(), _now(), user_id, provider),
        )
        await conn.commit()
        return cur.rowcount


# ── Single-flight refresh ───────────────────────────────────────────────────────

async def acquire_refresh_lease(connection_id: str, owner: str, ttl: int = 30) -> bool:
    """Try to become the one process refreshing this connection. True if we won.

    Compare-and-swap on an expiry timestamp, which is the same pattern
    `claim_ready_task` and `reclaim_expired_leases` already use. Correct across processes
    on SQLite because WAL serialises writers, and it survives the holder crashing because
    the lease expires rather than being released.

    A loser must not refresh. It waits, re-reads, and uses the winner's result — see
    `broker.fresh_access_token`.
    """
    now = _now()
    async with db.get_conn() as conn:
        row = await (
            await conn.execute(
                """UPDATE connections
                     SET refresh_lock_owner=?, refresh_lock_expires_at=?
                   WHERE id=?
                     AND (refresh_lock_expires_at IS NULL OR refresh_lock_expires_at < ?)
                   RETURNING id""",
                (owner, now + ttl, connection_id, now),
            )
        ).fetchone()
        await conn.commit()
    return row is not None


async def release_refresh_lease(connection_id: str, owner: str) -> None:
    """Release only if we still hold it — never clobber a lease that already expired to
    someone else, or two refreshes end up running anyway."""
    async with db.get_conn() as conn:
        await conn.execute(
            "UPDATE connections SET refresh_lock_owner=NULL, refresh_lock_expires_at=NULL "
            "WHERE id=? AND refresh_lock_owner=?",
            (connection_id, owner),
        )
        await conn.commit()


async def store_refreshed(
    connection_id: str, access_token: str, refresh_token: str,
    access_expires_at: int | None, user_id: str, provider: str,
) -> None:
    """Write a refreshed pair in ONE transaction.

    Both values together, always. The refresh token is single-use, so a crash between
    storing the new access token and storing the new refresh token leaves a connection
    holding a refresh token that has already been spent — unrecoverable without the user
    reconnecting.
    """
    kek_id, dek, wrapped = envelope.new_dek()
    access_ct, access_nonce = envelope.seal(
        dek, access_token, user_id=user_id, provider=provider, purpose="access")
    refresh_ct, refresh_nonce = envelope.seal(
        dek, refresh_token, user_id=user_id, provider=provider, purpose="refresh")
    now = _now()
    async with db.get_conn() as conn:
        await conn.execute(
            """UPDATE connections
                 SET kek_id=?, dek_wrapped=?, access_ct=?, access_nonce=?,
                     refresh_ct=?, refresh_nonce=?, access_expires_at=?,
                     refreshed_at=?, updated_at=?, status='active'
               WHERE id=?""",
            (kek_id, wrapped, access_ct, access_nonce, refresh_ct, refresh_nonce,
             access_expires_at, now, now, connection_id),
        )
        await conn.commit()


# ── Audit ───────────────────────────────────────────────────────────────────────

async def record_use(
    *, user_id: str, provider: str, agent_role: str = "", goal_id: str | None = None,
    task_id: str | None = None, connection_id: str | None = None, tool_name: str = "",
    target: str = "", token: str = "", outcome: str = "ok",
    provider_status: int | None = None, scopes: list[str] | None = None,
) -> None:
    """Append one row to the credential audit log.

    Written by the broker itself rather than by callers, which makes completeness
    structural: the broker is the only code that can decrypt a credential, so a use that
    does not appear here cannot have happened.

    `target` names the artifact — "acme/api#12" — because the question an audit log has to
    answer after an incident is not "did something happen" but "what do I have to undo".
    Never raises: an audit failure must not take down a goal.
    """
    try:
        async with db.get_conn() as conn:
            await conn.execute(
                """INSERT INTO credential_uses
                     (id, ts, user_id, agent_role, goal_id, task_id, connection_id,
                      provider, tool_name, target, scopes_at_call, token_fp, outcome,
                      provider_status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (f"use_{uuid.uuid4().hex[:26]}", _now(), user_id, agent_role, goal_id,
                 task_id, connection_id, provider, tool_name, target,
                 json.dumps(scopes or []), envelope.fingerprint(token), outcome,
                 provider_status),
            )
            await conn.commit()
    except Exception as e:
        logger.warning("failed to write credential_uses row: %s", e)


async def list_uses(user_id: str, limit: int = 100) -> list[dict]:
    async with db.get_conn() as conn:
        rows = await (
            await conn.execute(
                """SELECT * FROM credential_uses WHERE user_id=?
                   ORDER BY ts DESC LIMIT ?""",
                (user_id, limit),
            )
        ).fetchall()
    return [dict(r) for r in rows]
