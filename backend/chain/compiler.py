"""Compile the Mergit Solidity sources with solcx, caching artifacts by source hash.

Contracts are self-contained (no OpenZeppelin) so compilation needs nothing but solc.
"""
import hashlib
import json
import logging
from pathlib import Path

import solcx

logger = logging.getLogger(__name__)

SOLC_VERSION = "0.8.24"

CONTRACTS_DIR = Path(__file__).resolve().parent.parent / "contracts"
SRC_DIR = CONTRACTS_DIR / "src"
OUT_DIR = CONTRACTS_DIR / "out"

# Deployable contracts (Roles.sol is an abstract base and is intentionally absent)
CONTRACT_NAMES = ["AgentPassport", "ProofOfWork", "ReputationRegistry", "AuditTrail"]

_cache: dict | None = None


def _sources() -> list[Path]:
    return sorted(SRC_DIR.glob("*.sol"))


def source_hash() -> str:
    """Hash of every source file — the cache key."""
    h = hashlib.sha256()
    for path in _sources():
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def _ensure_solc() -> None:
    # solcx does not create SOLCX_BINARY_PATH itself — it fails with FileNotFoundError.
    # Containers set that variable to a baked-in location, so create it defensively.
    try:
        Path(solcx.get_solcx_install_folder()).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning("Could not prepare the solc install folder: %s", e)

    installed = {str(v) for v in solcx.get_installed_solc_versions()}
    if SOLC_VERSION not in installed:
        logger.info("Installing solc %s", SOLC_VERSION)
        solcx.install_solc(SOLC_VERSION)


def compile_all(force: bool = False) -> dict[str, dict]:
    """Return {name: {abi, bin}} for every deployable contract."""
    global _cache

    current = source_hash()
    if not force and _cache is not None and _cache.get("source_hash") == current:
        return _cache["contracts"]

    artifacts_file = OUT_DIR / "artifacts.json"
    if not force and artifacts_file.exists():
        try:
            cached = json.loads(artifacts_file.read_text())
            if cached.get("source_hash") == current:
                _cache = cached
                return cached["contracts"]
        except (json.JSONDecodeError, OSError):
            pass  # corrupt cache — recompile

    _ensure_solc()
    compiled = solcx.compile_files(
        [str(p) for p in _sources()],
        output_values=["abi", "bin"],
        solc_version=SOLC_VERSION,
        allow_paths=str(SRC_DIR),
        optimize=True,
        optimize_runs=200,
    )

    contracts: dict[str, dict] = {}
    for key, iface in compiled.items():
        name = key.rsplit(":", 1)[-1]
        if name in CONTRACT_NAMES:
            contracts[name] = {"abi": iface["abi"], "bin": iface["bin"]}

    missing = [n for n in CONTRACT_NAMES if n not in contracts]
    if missing:
        raise RuntimeError(f"Solidity compilation produced no artifact for: {', '.join(missing)}")

    payload = {"source_hash": current, "solc": SOLC_VERSION, "contracts": contracts}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    artifacts_file.write_text(json.dumps(payload, indent=2))
    for name, art in contracts.items():
        (OUT_DIR / f"{name}.json").write_text(json.dumps(art, indent=2))

    _cache = payload
    logger.info("Compiled %d contracts with solc %s", len(contracts), SOLC_VERSION)
    return contracts


def get(name: str) -> dict:
    """ABI + bytecode for a single contract."""
    artifacts = compile_all()
    if name not in artifacts:
        raise KeyError(f"Unknown contract {name!r}; known: {', '.join(sorted(artifacts))}")
    return artifacts[name]
