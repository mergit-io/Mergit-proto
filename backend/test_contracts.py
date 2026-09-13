"""Contract unit tests — real Solidity compiled by solc, executed on a real EVM (py-evm).

No RPC, no keys, no network, no tokens. Every assertion here is enforced by deployed
bytecode, not by Python.
"""
import pytest
from web3 import EthereumTesterProvider, Web3

from chain import compiler


@pytest.fixture(scope="module")
def artifacts():
    return compiler.compile_all()


@pytest.fixture()
def w3():
    return Web3(EthereumTesterProvider())


@pytest.fixture()
def admin(w3):
    return w3.eth.accounts[0]


@pytest.fixture()
def stranger(w3):
    return w3.eth.accounts[1]


def _deploy(w3, art, sender, *args):
    factory = w3.eth.contract(abi=art["abi"], bytecode=art["bin"])
    tx = factory.constructor(*args).transact({"from": sender})
    receipt = w3.eth.wait_for_transaction_receipt(tx)
    assert receipt.status == 1, "deployment reverted"
    return w3.eth.contract(address=receipt.contractAddress, abi=art["abi"])


def _send(w3, fn, sender):
    receipt = w3.eth.wait_for_transaction_receipt(fn.transact({"from": sender}))
    assert receipt.status == 1
    return receipt


def _assert_reverts(fn, sender):
    """A state-changing call that must be rejected by the contract."""
    with pytest.raises(Exception):
        fn.call({"from": sender})


@pytest.fixture()
def passport(w3, artifacts, admin):
    return _deploy(w3, artifacts["AgentPassport"], admin, admin)


@pytest.fixture()
def agent_token(w3, passport, admin):
    _send(w3, passport.functions.mint(
        w3.eth.accounts[5], "did:mergit:agent:coder", Web3.keccak(text="code_exec,file_ops")), admin)
    return passport.functions.agentToTokenId(w3.eth.accounts[5]).call()


# ── AgentPassport ───────────────────────────────────────────────────────────────

def test_passport_mints_with_identity(w3, passport, admin):
    owner = w3.eth.accounts[3]
    cap = Web3.keccak(text="web_search,http_request")
    receipt = _send(w3, passport.functions.mint(owner, "did:mergit:agent:researcher", cap), admin)

    event = passport.events.PassportMinted().process_receipt(receipt)[0]
    token_id = event["args"]["tokenId"]
    assert token_id == 1
    assert event["args"]["did"] == "did:mergit:agent:researcher"

    p = passport.functions.getPassport(token_id).call()
    assert p[1] == owner              # owner
    assert p[2] == "did:mergit:agent:researcher"
    assert p[3] == cap                # capabilityHash
    assert p[7] is True               # active
    assert passport.functions.balanceOf(owner).call() == 1


def test_passport_is_soulbound(w3, passport, admin, agent_token):
    owner = w3.eth.accounts[5]
    _assert_reverts(passport.functions.transferFrom(owner, w3.eth.accounts[6], agent_token), owner)
    _assert_reverts(passport.functions.approve(w3.eth.accounts[6], agent_token), owner)
    _assert_reverts(passport.functions.setApprovalForAll(w3.eth.accounts[6], True), owner)


def test_passport_one_per_address(w3, passport, admin, agent_token):
    _assert_reverts(
        passport.functions.mint(w3.eth.accounts[5], "did:mergit:agent:dup", Web3.keccak(text="x")), admin)


def test_passport_mint_requires_minter_role(w3, passport, stranger):
    _assert_reverts(
        passport.functions.mint(w3.eth.accounts[7], "did:mergit:agent:x", Web3.keccak(text="x")), stranger)


# ── ProofOfWork ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def pow_contract(w3, artifacts, admin, passport):
    c = _deploy(w3, artifacts["ProofOfWork"], admin, admin, passport.address)
    # ProofOfWork must be able to bump passport task counters
    _send(w3, passport.functions.grantRole(
        passport.functions.RECORDER_ROLE().call(), c.address), admin)
    return c


def test_record_proof_stores_and_emits(w3, pow_contract, admin, agent_token):
    task_id = Web3.keccak(text="goal1_t1")
    result_hash = Web3.keccak(text='{"result":"ok"}')

    receipt = _send(w3, pow_contract.functions.recordProof(task_id, agent_token, result_hash), admin)
    event = pow_contract.events.ProofRecorded().process_receipt(receipt)[0]

    assert event["args"]["taskId"] == task_id
    assert event["args"]["agentTokenId"] == agent_token
    assert event["args"]["resultHash"] == result_hash

    stored = pow_contract.functions.getProof(task_id).call()
    assert stored[0] == task_id
    assert stored[2] == result_hash
    assert pow_contract.functions.isRecorded(task_id).call() is True
    assert pow_contract.functions.proofCount().call() == 1


def test_record_proof_is_idempotent_onchain(w3, pow_contract, admin, agent_token):
    """The core integrity guarantee: a task can be proven exactly once, enforced by bytecode."""
    task_id = Web3.keccak(text="goal1_t1")
    result_hash = Web3.keccak(text='{"result":"ok"}')
    _send(w3, pow_contract.functions.recordProof(task_id, agent_token, result_hash), admin)

    _assert_reverts(pow_contract.functions.recordProof(task_id, agent_token, result_hash), admin)
    # ...and a different hash for the same task cannot overwrite history either
    _assert_reverts(
        pow_contract.functions.recordProof(task_id, agent_token, Web3.keccak(text="tampered")), admin)
    assert pow_contract.functions.proofCount().call() == 1


def test_record_proof_updates_passport_counters(w3, pow_contract, passport, admin, agent_token):
    _send(w3, pow_contract.functions.recordProof(
        Web3.keccak(text="t-a"), agent_token, Web3.keccak(text="ra")), admin)
    _send(w3, pow_contract.functions.recordProof(
        Web3.keccak(text="t-b"), agent_token, Web3.keccak(text="rb")), admin)

    p = passport.functions.getPassport(agent_token).call()
    assert p[4] == 2   # tasksCompleted
    assert p[5] == 2   # tasksAttempted


def test_record_proof_rejects_unknown_agent(w3, pow_contract, admin):
    _assert_reverts(
        pow_contract.functions.recordProof(Web3.keccak(text="t"), 999, Web3.keccak(text="r")), admin)


def test_record_proof_requires_recorder_role(w3, pow_contract, stranger, agent_token):
    _assert_reverts(
        pow_contract.functions.recordProof(
            Web3.keccak(text="t-x"), agent_token, Web3.keccak(text="r")), stranger)


def test_unrecorded_proof_reads_empty(w3, pow_contract):
    assert pow_contract.functions.isRecorded(Web3.keccak(text="never")).call() is False


# ── ReputationRegistry ──────────────────────────────────────────────────────────

@pytest.fixture()
def reputation(w3, artifacts, admin):
    return _deploy(w3, artifacts["ReputationRegistry"], admin, admin)


def test_first_score_has_no_delta_cap(w3, reputation, admin, agent_token):
    ch = Web3.keccak(text='{"success_rate":1.0}')
    receipt = _send(w3, reputation.functions.updateScore(agent_token, 9000, ch), admin)
    event = reputation.events.ScoreUpdated().process_receipt(receipt)[0]
    assert event["args"]["oldScore"] == 0
    assert event["args"]["newScore"] == 9000

    s = reputation.functions.getScore(agent_token).call()
    assert s[0] == 9000
    assert s[1] == ch


def test_score_delta_cap_enforced_onchain(w3, reputation, admin, agent_token):
    """PRD anti-manipulation rule: no more than 20% movement per update."""
    ch = Web3.keccak(text="c")
    _send(w3, reputation.functions.updateScore(agent_token, 5000, ch), admin)

    _send(w3, reputation.functions.updateScore(agent_token, 6000, ch), admin)   # +20% exactly: ok
    assert reputation.functions.getScore(agent_token).call()[0] == 6000

    _assert_reverts(reputation.functions.updateScore(agent_token, 9000, ch), admin)   # +50%: rejected
    _assert_reverts(reputation.functions.updateScore(agent_token, 1000, ch), admin)   # -83%: rejected


def test_score_range_enforced(w3, reputation, admin, agent_token):
    _assert_reverts(reputation.functions.updateScore(agent_token, 10001, Web3.keccak(text="c")), admin)


def test_score_requires_oracle_role(w3, reputation, stranger, agent_token):
    _assert_reverts(
        reputation.functions.updateScore(agent_token, 500, Web3.keccak(text="c")), stranger)


# ── AuditTrail ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def audit(w3, artifacts, admin):
    return _deploy(w3, artifacts["AuditTrail"], admin, admin)


def test_audit_logs_action_as_event(w3, audit, admin, agent_token):
    args_hash = Web3.keccak(text='{"repo":"mergit-io/mergit"}')
    result_hash = Web3.keccak(text='{"ok":true}')
    receipt = _send(w3, audit.functions.logAction(
        agent_token, "github_read_file", args_hash, result_hash), admin)

    event = audit.events.ActionLogged().process_receipt(receipt)[0]
    assert event["args"]["toolName"] == "github_read_file"
    assert event["args"]["argsHash"] == args_hash
    assert event["args"]["resultHash"] == result_hash


def test_audit_requires_writer_role(w3, audit, stranger, agent_token):
    _assert_reverts(
        audit.functions.logAction(agent_token, "code_exec", Web3.keccak(text="a"), Web3.keccak(text="r")),
        stranger)


# ── Compiler ────────────────────────────────────────────────────────────────────

def test_all_contracts_compile_with_bytecode(artifacts):
    for name in ["AgentPassport", "ProofOfWork", "ReputationRegistry", "AuditTrail"]:
        assert name in artifacts, f"{name} missing from compiled artifacts"
        assert artifacts[name]["bin"], f"{name} produced no bytecode"
        assert artifacts[name]["abi"], f"{name} produced no ABI"
