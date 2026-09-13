"""The credential vault, the refresh lease, and the human-in-the-loop gate.

These pin the three claims the delegated-authority design rests on:

  1. A stolen database row cannot be moved to another user, or between columns.
  2. Two workers cannot both spend a single-use refresh token.
  3. An agent cannot talk its way past an approval, because the gate is not in the prompt.
"""
import asyncio
import importlib
import os
import tempfile
import types

import pytest
from cryptography.exceptions import InvalidTag

from crypto import envelope


@pytest.fixture()
def vault(monkeypatch):
    """A configured key set, loaded the way the lifespan loads it."""
    monkeypatch.setenv("MERGIT_KEK_CURRENT", "dGVzdC1rZXktMzItYnl0ZXMtbG9uZy0hISEhISEh")
    envelope._KEYS.clear()
    envelope.load_keys_and_scrub_env()
    yield envelope
    envelope._KEYS.clear()


@pytest.fixture()
def store_env(monkeypatch, vault):
    tmp = tempfile.mkdtemp()
    import config
    monkeypatch.setattr(config.settings, "db_path", os.path.join(tmp, "cred.db"))
    import db as _db
    importlib.reload(_db)
    from credentials import store as _store
    importlib.reload(_store)
    monkeypatch.setattr(_store, "db", _db)
    asyncio.run(_db.init_db())
    return types.SimpleNamespace(db=_db, store=_store)


# ── The KEK must not survive startup ────────────────────────────────────────────

def test_the_kek_is_removed_from_the_environment(monkeypatch):
    """`PUT /api/config/keys` writes into os.environ and code_exec used to inherit it.

    A KEK left in the environment is one `print(os.environ)` away from unwrapping every
    stored OAuth token in the database.
    """
    monkeypatch.setenv("MERGIT_KEK_CURRENT", "some-key-material")
    envelope._KEYS.clear()
    envelope.load_keys_and_scrub_env()
    assert "MERGIT_KEK_CURRENT" not in os.environ
    assert envelope.configured()
    envelope._KEYS.clear()


def test_sealing_without_a_key_fails_loudly_rather_than_storing_plaintext():
    envelope._KEYS.clear()
    with pytest.raises(envelope.NoKeyConfigured):
        envelope.new_dek()


# ── Round trip ──────────────────────────────────────────────────────────────────

def test_a_sealed_token_round_trips(vault):
    kek_id, dek, wrapped = vault.new_dek()
    ct, nonce = vault.seal(dek, "ghp_secret", user_id="usr_1", provider="github",
                           purpose="access")
    assert b"ghp_secret" not in ct, "the plaintext is sitting in the ciphertext"

    same_dek = vault.unwrap_dek(kek_id, wrapped)
    out = vault.unseal(same_dek, ct, nonce, user_id="usr_1", provider="github",
                       purpose="access")
    assert out == "ghp_secret"


def test_each_seal_uses_a_fresh_nonce(vault):
    """GCM loses confidentiality AND authenticity on nonce reuse with the same key —
    which is exactly the risk when access and refresh share a DEK in one row."""
    _, dek, _ = vault.new_dek()
    _, n1 = vault.seal(dek, "a", user_id="u", provider="github", purpose="access")
    _, n2 = vault.seal(dek, "a", user_id="u", provider="github", purpose="refresh")
    assert n1 != n2


# ── The AAD binding: the reason this is not Fernet ──────────────────────────────

def test_a_ciphertext_moved_to_another_user_does_not_decrypt(vault):
    """Fernet exposes no associated data, so this attack works against it.

    An attacker with write access to the database moves Alice's sealed GitHub token into
    Bob's row. Without AAD the ciphertext is a free-floating blob and decrypts perfectly.
    """
    _, dek, _ = vault.new_dek()
    ct, nonce = vault.seal(dek, "ghp_alice", user_id="usr_alice", provider="github",
                           purpose="access")
    with pytest.raises(InvalidTag):
        vault.unseal(dek, ct, nonce, user_id="usr_bob", provider="github", purpose="access")


def test_a_refresh_ciphertext_cannot_be_pasted_into_the_access_column(vault):
    """`purpose` in the AAD. Both columns share a row and a DEK, so (user, provider) alone
    would not stop the swap — and refresh tokens are the more valuable of the two."""
    _, dek, _ = vault.new_dek()
    ct, nonce = vault.seal(dek, "ghr_refresh", user_id="u", provider="github",
                           purpose="refresh")
    with pytest.raises(InvalidTag):
        vault.unseal(dek, ct, nonce, user_id="u", provider="github", purpose="access")


def test_a_ciphertext_cannot_be_moved_between_providers(vault):
    _, dek, _ = vault.new_dek()
    ct, nonce = vault.seal(dek, "xoxb-slack", user_id="u", provider="slack",
                           purpose="access")
    with pytest.raises(InvalidTag):
        vault.unseal(dek, ct, nonce, user_id="u", provider="github", purpose="access")


def test_a_tampered_ciphertext_is_rejected(vault):
    _, dek, _ = vault.new_dek()
    ct, nonce = vault.seal(dek, "ghp_x", user_id="u", provider="github", purpose="access")
    flipped = bytes([ct[0] ^ 0x01]) + ct[1:]
    with pytest.raises(InvalidTag):
        vault.unseal(dek, flipped, nonce, user_id="u", provider="github", purpose="access")


def test_key_rotation_keeps_old_rows_readable(monkeypatch):
    """`kek_id` per row is what makes rotation a re-wrap rather than a table rewrite."""
    monkeypatch.setenv("MERGIT_KEK_CURRENT", "original-key-material")
    envelope._KEYS.clear()
    envelope.load_keys_and_scrub_env()
    old_id, old_dek, old_wrapped = envelope.new_dek()
    ct, nonce = envelope.seal(old_dek, "ghp_old", user_id="u", provider="github",
                              purpose="access")

    # Rotate: a new current key, the old one retained as previous.
    monkeypatch.setenv("MERGIT_KEK_CURRENT", "brand-new-key-material")
    monkeypatch.setenv("MERGIT_KEK_PREVIOUS", f"{old_id}:original-key-material")
    envelope._KEYS.clear()
    envelope.load_keys_and_scrub_env()

    recovered = envelope.unwrap_dek(old_id, old_wrapped)
    assert envelope.unseal(recovered, ct, nonce, user_id="u", provider="github",
                           purpose="access") == "ghp_old"
    envelope._KEYS.clear()


def test_a_fingerprint_identifies_without_revealing(vault):
    fp = vault.fingerprint("ghp_secret_token")
    assert fp and "ghp_" not in fp and len(fp) == 16
    assert fp == vault.fingerprint("ghp_secret_token"), "must be stable across calls"
    assert fp != vault.fingerprint("ghp_other_token")


# ── The store ───────────────────────────────────────────────────────────────────

def test_a_stored_connection_round_trips(store_env):
    async def scenario():
        await store_env.store.upsert_connection(
            user_id="usr_legacy_demo", provider="github",
            external_account_id="octocat", access_token="ghu_abc",
            refresh_token="ghr_xyz", display_name="Octo Cat",
        )
        conn = await store_env.store.get_connection("usr_legacy_demo", "github")
        assert conn is not None
        access, refresh = store_env.store.open_secrets(conn)
        assert (access, refresh) == ("ghu_abc", "ghr_xyz")
    asyncio.run(scenario())


def test_the_stored_row_holds_no_plaintext(store_env):
    """The whole point: someone who reads the database file gets ciphertext."""
    async def scenario():
        await store_env.store.upsert_connection(
            user_id="usr_legacy_demo", provider="github",
            external_account_id="octocat", access_token="ghu_VERYSECRET",
        )
        async with store_env.db.get_conn() as conn:
            row = await (await conn.execute("SELECT * FROM connections")).fetchone()
        blob = b"".join(v for v in dict(row).values() if isinstance(v, bytes))
        text = " ".join(str(v) for v in dict(row).values())
        assert b"ghu_VERYSECRET" not in blob
        assert "ghu_VERYSECRET" not in text
    asyncio.run(scenario())


def test_listing_connections_never_returns_a_token(store_env):
    """Not even masked. A masked provider key is right for Mergit's own keys and wrong for
    a credential held on someone's behalf — there is nothing for the user to copy."""
    async def scenario():
        await store_env.store.upsert_connection(
            user_id="usr_legacy_demo", provider="github",
            external_account_id="octocat", access_token="ghu_abc", refresh_token="ghr_x",
        )
        listed = await store_env.store.list_connections("usr_legacy_demo")
        flat = str(listed)
        assert "ghu_" not in flat and "ghr_" not in flat
        assert listed[0]["account"] == "octocat"
    asyncio.run(scenario())


def test_reconnecting_replaces_rather_than_duplicates(store_env):
    async def scenario():
        for token in ("ghu_first", "ghu_second"):
            await store_env.store.upsert_connection(
                user_id="usr_legacy_demo", provider="github",
                external_account_id="octocat", access_token=token)
        conns = await store_env.store.list_connections("usr_legacy_demo")
        assert len(conns) == 1
        access, _ = store_env.store.open_secrets(
            await store_env.store.get_connection("usr_legacy_demo", "github"))
        assert access == "ghu_second"
    asyncio.run(scenario())


# ── Single-flight refresh ───────────────────────────────────────────────────────

def test_only_one_worker_wins_the_refresh_lease(store_env):
    """GitHub's ghr_ and Slack's xoxe- are SINGLE USE.

    Two concurrent refreshes do not merely duplicate work — the second redemption fails
    and the connection is permanently bricked until the user reconnects.
    """
    async def scenario():
        conn_id = await store_env.store.upsert_connection(
            user_id="usr_legacy_demo", provider="github",
            external_account_id="octocat", access_token="a", refresh_token="r")

        first = await store_env.store.acquire_refresh_lease(conn_id, "worker-a")
        second = await store_env.store.acquire_refresh_lease(conn_id, "worker-b")
        assert first is True
        assert second is False, "two workers both believed they held the refresh lease"

        await store_env.store.release_refresh_lease(conn_id, "worker-a")
        assert await store_env.store.acquire_refresh_lease(conn_id, "worker-b") is True
    asyncio.run(scenario())


def test_a_lease_expires_so_a_crashed_worker_does_not_block_forever(store_env):
    async def scenario():
        conn_id = await store_env.store.upsert_connection(
            user_id="usr_legacy_demo", provider="github",
            external_account_id="octocat", access_token="a", refresh_token="r")
        assert await store_env.store.acquire_refresh_lease(conn_id, "crashed", ttl=-1)
        # The holder never released it, but the lease is already past its expiry.
        assert await store_env.store.acquire_refresh_lease(conn_id, "next") is True
    asyncio.run(scenario())


def test_releasing_a_lease_you_no_longer_hold_is_a_no_op(store_env):
    """Otherwise a slow worker whose lease expired would clear the new holder's lease and
    two refreshes would run anyway — the exact thing the lease exists to prevent."""
    async def scenario():
        conn_id = await store_env.store.upsert_connection(
            user_id="usr_legacy_demo", provider="github",
            external_account_id="octocat", access_token="a", refresh_token="r")
        await store_env.store.acquire_refresh_lease(conn_id, "worker-a", ttl=-1)
        await store_env.store.acquire_refresh_lease(conn_id, "worker-b")
        await store_env.store.release_refresh_lease(conn_id, "worker-a")   # the stale one
        assert await store_env.store.acquire_refresh_lease(conn_id, "worker-c") is False
    asyncio.run(scenario())


# ── Audit ───────────────────────────────────────────────────────────────────────

def test_the_audit_log_records_the_artifact_not_the_token(store_env):
    async def scenario():
        await store_env.store.record_use(
            user_id="usr_legacy_demo", provider="github", tool_name="github_merge_pr",
            target="acme/api#12", token="ghu_secret", agent_role="integrator")
        uses = await store_env.store.list_uses("usr_legacy_demo")
        assert len(uses) == 1
        # "what do I have to undo" is the question an audit log exists to answer.
        assert uses[0]["target"] == "acme/api#12"
        assert "ghu_secret" not in str(uses[0])
        assert uses[0]["token_fp"], "a fingerprint is still needed to correlate uses"
    asyncio.run(scenario())


def test_an_audit_failure_never_breaks_a_goal(store_env, monkeypatch):
    def boom(*a, **k):
        # Sync, so the failure happens at `async with` rather than producing an
        # un-awaited coroutine warning that masks what is being tested.
        raise RuntimeError("disk full")
    monkeypatch.setattr(store_env.store.db, "get_conn", boom)
    # Must not raise.
    asyncio.run(store_env.store.record_use(
        user_id="u", provider="github", tool_name="x", token="t"))


# ── The approval gate ───────────────────────────────────────────────────────────

@pytest.fixture()
def gate_env(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    monkeypatch.setattr(config.settings, "db_path", os.path.join(tmp, "approve.db"))
    import db as _db
    importlib.reload(_db)
    from tools import approval as _approval
    importlib.reload(_approval)
    monkeypatch.setattr(_approval, "db", _db)
    asyncio.run(_db.init_db())
    return types.SimpleNamespace(db=_db, approval=_approval)


async def _task_for(gate_env, user_id="usr_legacy_demo"):
    goal = await gate_env.db.create_goal("do a risky thing", user_id=user_id)
    tasks = await gate_env.db.create_tasks(
        [{"id": "t1", "agent": "integrator", "description": "merge it",
          "inputs": {}, "depends_on": []}],
        goal.id, goal.trace_id)
    return goal, tasks[0]


MERGE_ARGS = {"repo": "acme/api", "pr_number": 12, "merge_method": "squash"}


def test_a_reversible_action_is_not_gated(gate_env):
    """The gate is on the hot path of every tool call. Opening a PR is a nuisance to undo,
    not an irreversible act — gating it would put a human in the main pipeline."""
    async def scenario():
        _, task = await _task_for(gate_env)
        await gate_env.approval.check(task, "github_pr", {"repo": "acme/api"})
        await gate_env.approval.check(task, "github_post_comment", {"repo": "acme/api"})
    asyncio.run(scenario())


def test_an_irreversible_action_parks_for_a_human(gate_env):
    async def scenario():
        _, task = await _task_for(gate_env)
        with pytest.raises(gate_env.approval.ApprovalRequired) as caught:
            await gate_env.approval.check(task, "github_merge_pr", MERGE_ARGS)
        assert "Merge pull request #12 in acme/api" in caught.value.summary
        assert caught.value.credential_key.startswith("approval:")
    asyncio.run(scenario())


def test_an_approved_action_proceeds(gate_env):
    async def scenario():
        _, task = await _task_for(gate_env)
        with pytest.raises(gate_env.approval.ApprovalRequired) as caught:
            await gate_env.approval.check(task, "github_merge_pr", MERGE_ARGS)
        await gate_env.approval.decide(caught.value.approval_id, "usr_legacy_demo", "approve")
        await gate_env.approval.check(task, "github_merge_pr", MERGE_ARGS)  # must not raise
    asyncio.run(scenario())


def test_a_denial_is_terminal_and_tells_the_agent_to_stop(gate_env):
    async def scenario():
        _, task = await _task_for(gate_env)
        with pytest.raises(gate_env.approval.ApprovalRequired) as caught:
            await gate_env.approval.check(task, "github_merge_pr", MERGE_ARGS)
        await gate_env.approval.decide(caught.value.approval_id, "usr_legacy_demo", "deny")

        with pytest.raises(PermissionError) as denied:
            await gate_env.approval.check(task, "github_merge_pr", MERGE_ARGS)
        assert "final" in str(denied.value).lower()
    asyncio.run(scenario())


def test_approval_is_bound_to_the_exact_arguments(gate_env):
    """The heart of the injection defence.

    Approving "merge PR #12" must not authorise "merge PR #99". Without the args hash an
    approval is a standing grant on a tool NAME — and changing the arguments is precisely
    what a prompt-injection attack does.
    """
    async def scenario():
        _, task = await _task_for(gate_env)
        with pytest.raises(gate_env.approval.ApprovalRequired) as caught:
            await gate_env.approval.check(task, "github_merge_pr", MERGE_ARGS)
        await gate_env.approval.decide(caught.value.approval_id, "usr_legacy_demo", "approve")

        other = {**MERGE_ARGS, "pr_number": 99}
        with pytest.raises(gate_env.approval.ApprovalRequired):
            await gate_env.approval.check(task, "github_merge_pr", other)
    asyncio.run(scenario())


def test_the_runner_injected_goal_id_is_not_part_of_what_is_approved(gate_env):
    """`_goal_id` is added by the runner, not by the model, and is not something a human
    is agreeing to — including it would make identical actions hash differently."""
    a = gate_env.approval.args_fingerprint(MERGE_ARGS)
    b = gate_env.approval.args_fingerprint({**MERGE_ARGS, "_goal_id": "abc"})
    assert a == b


def test_argument_order_does_not_change_the_fingerprint(gate_env):
    a = gate_env.approval.args_fingerprint({"repo": "x", "pr_number": 1})
    b = gate_env.approval.args_fingerprint({"pr_number": 1, "repo": "x"})
    assert a == b


def test_a_second_decision_returns_the_first_outcome(gate_env):
    """Single use. Otherwise a leaked approval id could be flipped after the fact."""
    async def scenario():
        _, task = await _task_for(gate_env)
        with pytest.raises(gate_env.approval.ApprovalRequired) as caught:
            await gate_env.approval.check(task, "github_merge_pr", MERGE_ARGS)
        aid = caught.value.approval_id
        first = await gate_env.approval.decide(aid, "usr_legacy_demo", "deny")
        second = await gate_env.approval.decide(aid, "usr_legacy_demo", "approve")
        assert first["decision"] == "deny"
        assert second["decision"] == "deny", "a decided approval must not be re-decided"
    asyncio.run(scenario())


def test_another_user_cannot_decide_your_approval(gate_env):
    async def scenario():
        _, task = await _task_for(gate_env)
        with pytest.raises(gate_env.approval.ApprovalRequired) as caught:
            await gate_env.approval.check(task, "github_merge_pr", MERGE_ARGS)
        # usr_mergit_system exists but does not own this goal.
        assert await gate_env.approval.decide(
            caught.value.approval_id, "usr_mergit_system", "approve") is None
    asyncio.run(scenario())


def test_an_expired_request_counts_as_a_refusal(gate_env):
    """The agent is asking to do something irreversible while the person who could say no
    is asleep. Silence is not consent."""
    async def scenario():
        _, task = await _task_for(gate_env)
        with pytest.raises(gate_env.approval.ApprovalRequired) as caught:
            await gate_env.approval.check(task, "github_merge_pr", MERGE_ARGS)
        async with gate_env.db.get_conn() as conn:
            await conn.execute("UPDATE approvals SET expires_at=1 WHERE id=?",
                               (caught.value.approval_id,))
            await conn.commit()
        with pytest.raises(PermissionError):
            await gate_env.approval.check(task, "github_merge_pr", MERGE_ARGS)
    asyncio.run(scenario())


def test_closing_a_pr_is_gated_but_editing_its_title_is_not(gate_env):
    """`github_update_pr` is only irreversible in one of its modes."""
    async def scenario():
        _, task = await _task_for(gate_env)
        await gate_env.approval.check(task, "github_update_pr",
                                      {"repo": "a/b", "pr_number": 1, "title": "new title"})
        with pytest.raises(gate_env.approval.ApprovalRequired):
            await gate_env.approval.check(task, "github_update_pr",
                                          {"repo": "a/b", "pr_number": 1, "state": "closed"})
    asyncio.run(scenario())


def test_the_summary_is_readable_by_a_human(gate_env):
    """An approval prompt showing a tool name and a JSON blob gets approved reflexively,
    which is the same as having no gate."""
    s = gate_env.approval.summarise("github_merge_pr", MERGE_ARGS)
    assert s == "Merge pull request #12 in acme/api using squash"
    assert "PUBLIC" in gate_env.approval.summarise(
        "github_create_repo", {"name": "thing", "private": False})
