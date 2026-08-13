"""ChainClient — the app-facing chain API.

Every method degrades rather than raises: a chain that is down, undeployed or misconfigured
must never break a goal run. Callers get `None` and carry on; the outbox retries later.
"""
import hashlib
import logging
from enum import Enum

from web3 import Web3

from . import compiler, networks, registry
from .provider import ChainSendError, build_provider

logger = logging.getLogger(__name__)

CONTRACT_NAMES = ["AgentPassport", "ProofOfWork", "ReputationRegistry", "AuditTrail"]


class ChainStatus(str, Enum):
    DISABLED = "disabled"
    NOT_DEPLOYED = "not_deployed"
    READY = "ready"
    ERROR = "error"


def role_address(role: str) -> str:
    """Deterministic mock owner address for an agent role.

    MUST stay identical to `economy.owner_address` — the passport minted here is the same
    identity the economy layer displays. `test_chain_client` asserts the two agree.
    """
    return Web3.to_checksum_address("0x" + hashlib.sha256(role.encode()).hexdigest()[:40])


class ChainClient:
    def __init__(self, provider, addresses: dict[str, str] | None):
        self.provider = provider
        self.network = provider.network
        self.addresses = dict(addresses or {})
        self._contracts: dict = {}
        self._passport_cache: dict[str, int] = {}
        self.error: str | None = None

        if not all(self.addresses.get(name) for name in CONTRACT_NAMES):
            self.status = ChainStatus.NOT_DEPLOYED
            return

        try:
            artifacts = compiler.compile_all()
            for name in CONTRACT_NAMES:
                address = Web3.to_checksum_address(self.addresses[name])
                # Binding a contract is pure local ABI work and succeeds against any
                # address. Only bytecode on the chain proves the deployment is real —
                # without this, a stale or invented deployments/{chainId}.json would
                # report READY and the UI would announce a network we are not on.
                if not provider.w3.eth.get_code(address):
                    logger.warning("No contract code at %s for %s on chain %s — treating "
                                   "this chain as not deployed", address, name,
                                   provider.chain_id)
                    self.status = ChainStatus.NOT_DEPLOYED
                    self._contracts.clear()
                    return
                self._contracts[name] = provider.w3.eth.contract(
                    address=address, abi=artifacts[name]["abi"],
                )
            self.status = ChainStatus.READY
        except Exception as e:
            logger.error("ChainClient init failed: %s", e)
            self.error = str(e)
            self.status = ChainStatus.ERROR

    # ── Construction ────────────────────────────────────────────────────────────

    @classmethod
    def create(cls, target: str, rpc_url: str = "", private_key: str = "",
               addresses: dict | None = None) -> "ChainClient | None":
        """Build a client for a chain target, or None if the provider cannot be constructed."""
        try:
            provider = build_provider(target, rpc_url, private_key)
        except Exception as e:
            logger.warning("Chain provider unavailable for target %r: %s", target, e)
            return None
        if addresses is None:
            addresses = registry.load_addresses(provider.chain_id)
        return cls(provider, addresses)

    # ── Properties ──────────────────────────────────────────────────────────────

    @property
    def is_ready(self) -> bool:
        return self.status == ChainStatus.READY

    @property
    def chain_id(self) -> int:
        return self.provider.chain_id

    def info(self) -> dict:
        return {
            **self.network.to_dict(),
            "status": self.status.value,
            "contracts": self.addresses,
            "sender": getattr(self.provider, "sender_address", None),
            "error": self.error,
        }

    # ── Hash helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def task_key(task_id: str) -> bytes:
        """Task ids are arbitrary strings; the chain keys on keccak256 of them."""
        return Web3.keccak(text=task_id)

    @staticmethod
    def hash_to_bytes32(hex_hash: str) -> bytes:
        raw = hex_hash[2:] if hex_hash.startswith("0x") else hex_hash
        if len(raw) != 64:
            raise ValueError(f"expected a 32-byte hex hash, got {len(raw)} chars")
        return bytes.fromhex(raw)

    @staticmethod
    def _b32_hex(value: bytes) -> str:
        return value.hex()

    # ── Passports ───────────────────────────────────────────────────────────────

    def ensure_passport(self, role: str, capabilities: list[str] | None = None) -> int | None:
        """Token id for a role, minting the passport on first use. Idempotent."""
        if not self.is_ready:
            return None
        if role in self._passport_cache:
            return self._passport_cache[role]

        passport = self._contracts["AgentPassport"]
        owner = role_address(role)
        try:
            existing = passport.functions.agentToTokenId(owner).call()
            if existing:
                self._passport_cache[role] = existing
                return existing

            cap_hash = Web3.keccak(text=",".join(sorted(capabilities or [])))
            self.provider.send(
                passport.functions.mint(owner, f"did:mergit:agent:{role}", cap_hash)
            )
            token_id = passport.functions.agentToTokenId(owner).call()
            self._passport_cache[role] = token_id
            logger.info("Minted passport #%s for role %s", token_id, role)
            return token_id
        except Exception as e:
            logger.warning("ensure_passport(%s) failed: %s", role, e)
            return None

    # ── Proofs ──────────────────────────────────────────────────────────────────

    def record_proof(self, task_id: str, role: str, result_hash: str) -> dict | None:
        """Record a task proof on chain.

        Returns a receipt dict, or None on failure. A task already recorded returns a
        receipt with `already_recorded=True` — that is success, not failure: the chain
        enforcing idempotency is the point.
        """
        if not self.is_ready:
            return None

        try:
            key = self.task_key(task_id)
            pow_contract = self._contracts["ProofOfWork"]

            if pow_contract.functions.isRecorded(key).call():
                existing = self.get_proof(task_id) or {}
                return {
                    "tx_hash": existing.get("tx_hash"),
                    "block_number": existing.get("block_number"),
                    "chain_id": self.chain_id,
                    "gas_used": 0,
                    "already_recorded": True,
                }

            token_id = self.ensure_passport(role)
            if not token_id:
                logger.warning("record_proof: no passport for role %s", role)
                return None

            receipt = self.provider.send(
                pow_contract.functions.recordProof(
                    key, token_id, self.hash_to_bytes32(result_hash)
                )
            )
            return {
                "tx_hash": receipt["tx_hash"],
                "block_number": receipt["block_number"],
                "gas_used": receipt["gas_used"],
                "chain_id": self.chain_id,
                "already_recorded": False,
            }
        except ChainSendError as e:
            logger.warning("record_proof(%s) reverted: %s", task_id, e)
            return None
        except Exception as e:
            logger.warning("record_proof(%s) failed: %s", task_id, e)
            return None

    def get_proof(self, task_id: str) -> dict | None:
        if not self.is_ready:
            return None
        try:
            raw = self._contracts["ProofOfWork"].functions.getProof(self.task_key(task_id)).call()
            if not raw or raw[0] == b"\x00" * 32:
                return None
            return {
                "task_key": self._b32_hex(raw[0]),
                "agent_token_id": raw[1],
                "result_hash": self._b32_hex(raw[2]),
                "recorded_at": raw[3],
                "block_number": raw[4],
                "chain_id": self.chain_id,
            }
        except Exception as e:
            logger.warning("get_proof(%s) failed: %s", task_id, e)
            return None

    def verify(self, task_id: str, expected_result_hash: str) -> bool:
        """Does the chain agree with a locally recomputed hash?"""
        if not self.is_ready:
            return False
        try:
            return bool(
                self._contracts["ProofOfWork"].functions.verify(
                    self.task_key(task_id), self.hash_to_bytes32(expected_result_hash)
                ).call()
            )
        except Exception as e:
            logger.warning("verify(%s) failed: %s", task_id, e)
            return False

    # ── Reputation ──────────────────────────────────────────────────────────────

    def update_score(self, role: str, score: int, component_hash: str) -> dict | None:
        if not self.is_ready:
            return None
        token_id = self.ensure_passport(role)
        if not token_id:
            return None
        try:
            receipt = self.provider.send(
                self._contracts["ReputationRegistry"].functions.updateScore(
                    token_id, int(score), self.hash_to_bytes32(component_hash)
                )
            )
            return {
                "tx_hash": receipt["tx_hash"],
                "block_number": receipt["block_number"],
                "chain_id": self.chain_id,
            }
        except ChainSendError as e:
            # Most often the on-chain 20% delta guard rejecting the move — expected, not a bug.
            logger.info("update_score(%s → %s) rejected: %s", role, score, e)
            return None
        except Exception as e:
            logger.warning("update_score(%s) failed: %s", role, e)
            return None

    def get_score(self, role: str) -> dict | None:
        if not self.is_ready:
            return None
        token_id = self.ensure_passport(role)
        if not token_id:
            return None
        try:
            raw = self._contracts["ReputationRegistry"].functions.getScore(token_id).call()
            return {
                "score": raw[0],
                "component_hash": self._b32_hex(raw[1]),
                "updated_at": raw[2],
                "update_count": raw[3],
            }
        except Exception as e:
            logger.warning("get_score(%s) failed: %s", role, e)
            return None

    # ── Audit ───────────────────────────────────────────────────────────────────

    def log_action(self, role: str, tool_name: str, args_hash: str, result_hash: str) -> dict | None:
        if not self.is_ready:
            return None
        token_id = self.ensure_passport(role)
        if not token_id:
            return None
        try:
            receipt = self.provider.send(
                self._contracts["AuditTrail"].functions.logAction(
                    token_id, tool_name,
                    self.hash_to_bytes32(args_hash), self.hash_to_bytes32(result_hash),
                )
            )
            return {
                "tx_hash": receipt["tx_hash"],
                "block_number": receipt["block_number"],
                "chain_id": self.chain_id,
            }
        except Exception as e:
            logger.warning("log_action(%s/%s) failed: %s", role, tool_name, e)
            return None

    # ── Explorer ────────────────────────────────────────────────────────────────

    def tx_url(self, tx_hash: str) -> str | None:
        return self.network.tx_url(tx_hash) if tx_hash else None


_client: ChainClient | None = None
_initialized = False


def get_client() -> ChainClient | None:
    """Process-wide client built from config. None when chain support is off."""
    global _client, _initialized
    if _initialized:
        return _client

    from config import settings

    _initialized = True
    if not getattr(settings, "chain_enabled", True):
        _client = None
        return None

    _client = ChainClient.create(
        target=getattr(settings, "chain_target", networks.DEFAULT_NETWORK_KEY),
        rpc_url=getattr(settings, "chain_rpc_url", ""),
        private_key=getattr(settings, "chain_private_key", ""),
    )
    return _client


def set_client(client: ChainClient | None) -> None:
    """Install a client explicitly (startup auto-deploy, tests)."""
    global _client, _initialized
    _client = client
    _initialized = True


def reset_client() -> None:
    global _client, _initialized
    _client = None
    _initialized = False
