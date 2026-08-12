"""Chain client tests — the app-facing API over a real EVM.

Everything here runs on an in-process chain: no RPC URL, no private key, no network.
"""
import pytest

from chain import networks
from chain.client import ChainClient, ChainStatus
from chain.deployer import deploy_all
from chain.provider import LocalEvmProvider

RESULT_HASH = "a" * 64  # sha256 hex, as economy.result_hash produces


@pytest.fixture()
def client():
    provider = LocalEvmProvider()
    addresses = deploy_all(provider)
    return ChainClient(provider, addresses)


# ── Wiring ──────────────────────────────────────────────────────────────────────

def test_client_is_ready_after_deploy(client):
    assert client.status == ChainStatus.READY
    assert client.is_ready
    assert client.chain_id == networks.LOCAL.chain_id
    for name in ["AgentPassport", "ProofOfWork", "ReputationRegistry", "AuditTrail"]:
        assert client.addresses[name].startswith("0x")


def test_client_without_deployment_is_not_ready():
    client = ChainClient(LocalEvmProvider(), {})
    assert client.status == ChainStatus.NOT_DEPLOYED
    assert not client.is_ready
    # Must degrade, not explode — the app has to keep running.
    assert client.record_proof("t1", "coder", RESULT_HASH) is None
    assert client.get_proof("t1") is None


# ── Hash conversion ─────────────────────────────────────────────────────────────

def test_task_id_conversion_is_deterministic_and_collision_free():
    a = ChainClient.task_key("goal1_t1")
    assert a == ChainClient.task_key("goal1_t1")
    assert a != ChainClient.task_key("goal1_t2")
    assert len(a) == 32


def test_result_hash_conversion_round_trips():
    raw = ChainClient.hash_to_bytes32(RESULT_HASH)
    assert len(raw) == 32
    assert raw.hex() == RESULT_HASH
    # tolerate a 0x prefix
    assert ChainClient.hash_to_bytes32("0x" + RESULT_HASH) == raw


# ── Passports ───────────────────────────────────────────────────────────────────

def test_ensure_passport_mints_once_per_role(client):
    first = client.ensure_passport("coder")
    second = client.ensure_passport("coder")
    assert first == second, "a role must not receive two passports"
    assert first > 0
    assert client.ensure_passport("researcher") != first


# ── Proofs ──────────────────────────────────────────────────────────────────────

def test_record_proof_returns_real_transaction(client):
    receipt = client.record_proof("goal1_t1", "coder", RESULT_HASH)

    assert receipt is not None
    assert receipt["tx_hash"].startswith("0x")
    assert len(receipt["tx_hash"]) == 66          # real 32-byte tx hash
    assert receipt["block_number"] > 0
    assert receipt["chain_id"] == networks.LOCAL.chain_id
    assert receipt["already_recorded"] is False
    assert receipt["gas_used"] > 0


def test_recorded_proof_is_readable_from_chain(client):
    client.record_proof("goal1_t1", "coder", RESULT_HASH)
    proof = client.get_proof("goal1_t1")

    assert proof is not None
    assert proof["result_hash"] == RESULT_HASH
    assert proof["block_number"] > 0
    assert proof["agent_token_id"] == client.ensure_passport("coder")


def test_duplicate_proof_is_benign_not_fatal(client):
    """Re-submission happens on worker restart/reclaim — it must not look like a failure."""
    first = client.record_proof("goal1_t1", "coder", RESULT_HASH)
    second = client.record_proof("goal1_t1", "coder", RESULT_HASH)

    assert first["already_recorded"] is False
    assert second is not None, "duplicate must not return None (that means failure)"
    assert second["already_recorded"] is True


def test_tampered_output_does_not_verify(client):
    client.record_proof("goal1_t1", "coder", RESULT_HASH)
    assert client.verify("goal1_t1", RESULT_HASH) is True
    assert client.verify("goal1_t1", "b" * 64) is False


def test_unknown_task_has_no_proof(client):
    assert client.get_proof("never-ran") is None
    assert client.verify("never-ran", RESULT_HASH) is False


# ── Reputation + audit ──────────────────────────────────────────────────────────

def test_update_score_writes_and_reads_back(client):
    client.ensure_passport("coder")
    receipt = client.update_score("coder", 9000, "c" * 64)
    assert receipt["tx_hash"].startswith("0x")

    score = client.get_score("coder")
    assert score["score"] == 9000
    assert score["component_hash"] == "c" * 64


def test_update_score_rejects_illegal_delta(client):
    client.ensure_passport("coder")
    client.update_score("coder", 5000, "c" * 64)
    # +80% violates the on-chain 20% guard; the client surfaces it as a failure, not a crash
    assert client.update_score("coder", 9000, "c" * 64) is None
    assert client.get_score("coder")["score"] == 5000


def test_log_action_emits_audit_event(client):
    client.ensure_passport("coder")
    receipt = client.log_action("coder", "github_read_file", "d" * 64, "e" * 64)
    assert receipt["tx_hash"].startswith("0x")
    assert receipt["block_number"] > 0


# ── Explorer links ──────────────────────────────────────────────────────────────

def test_monad_explorer_url_built_correctly():
    monad = networks.get_network("monad-testnet")
    assert monad.chain_id == 10143
    assert monad.tx_url("0xabc") == "https://testnet.monadexplorer.com/tx/0xabc"
    assert networks.LOCAL.tx_url("0xabc") is None  # local chain has no explorer


def test_networks_lookup_by_chain_id():
    assert networks.by_chain_id(10143) is networks.MONAD_TESTNET
    assert networks.by_chain_id(31337) is networks.LOCAL
    assert networks.by_chain_id(999999) is None


# ── Cross-module invariant ──────────────────────────────────────────────────────

def test_chain_and_economy_agree_on_agent_addresses():
    """`chain.client.role_address` intentionally duplicates `economy.owner_address` to keep
    the chain package free of app imports. This test is what makes that duplication safe."""
    import economy
    from chain.client import role_address

    for role in economy.ROLES:
        assert role_address(role).lower() == economy.owner_address(role).lower(), (
            f"address derivation diverged for role {role!r} — the on-chain passport would "
            f"no longer match the identity the economy UI displays"
        )
