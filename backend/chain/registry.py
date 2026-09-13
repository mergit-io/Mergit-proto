"""Deployment address registry — `backend/deployments/{chain_id}.json`.

Keeps the schema the existing `/api/economy/chain` endpoint already serves, so the frontend
needs no change to start reading real addresses instead of the invented ones.
"""
import json
import logging
from pathlib import Path

from . import networks

logger = logging.getLogger(__name__)

DEPLOYMENTS_DIR = Path(__file__).resolve().parent.parent / "deployments"

CONTRACT_NAMES = ["AgentPassport", "ProofOfWork", "ReputationRegistry", "AuditTrail"]


def path_for(chain_id: int) -> Path:
    return DEPLOYMENTS_DIR / f"{chain_id}.json"


def load(chain_id: int) -> dict | None:
    """Full deployment record, or None when this chain has never been deployed to."""
    path = path_for(chain_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Unreadable deployment file %s: %s", path, e)
        return None


def load_addresses(chain_id: int) -> dict[str, str]:
    """Contract addresses only. Empty dict when not deployed or incomplete."""
    record = load(chain_id)
    if not record:
        return {}
    contracts = record.get("contracts") or {}
    if not all(contracts.get(name) for name in CONTRACT_NAMES):
        return {}
    return {name: contracts[name] for name in CONTRACT_NAMES}


def save(chain_id: int, addresses: dict[str, str], deployer: str = "", block: int | None = None) -> Path:
    network = networks.by_chain_id(chain_id)
    record = {
        "chainId": chain_id,
        "network": network.name if network else f"chain-{chain_id}",
        "explorer": (network.explorer_base if network else "") or None,
        "deployer": deployer,
        "deployedAtBlock": block,
        "contracts": {name: addresses[name] for name in CONTRACT_NAMES if name in addresses},
    }
    DEPLOYMENTS_DIR.mkdir(parents=True, exist_ok=True)
    path = path_for(chain_id)
    path.write_text(json.dumps(record, indent=2) + "\n")
    logger.info("Wrote deployment record %s", path)
    return path
