"""Deploy the Mergit contract set in dependency order and wire up roles.

Used by both the test fixtures (local EVM) and `scripts/deploy_contracts.py` (any network),
so the deployment the tests exercise is the same one that ships.
"""
import logging

from . import compiler, registry

logger = logging.getLogger(__name__)


def deploy_all(provider, persist: bool = False) -> dict[str, str]:
    """Deploy all contracts, grant cross-contract roles, return {name: address}.

    Order matters: ProofOfWork takes the passport address in its constructor, and must then
    be granted RECORDER_ROLE so it can advance passport task counters.
    """
    artifacts = compiler.compile_all()
    admin = provider.sender_address
    addresses: dict[str, str] = {}

    passport_abi = artifacts["AgentPassport"]["abi"]
    addresses["AgentPassport"] = provider.deploy(
        passport_abi, artifacts["AgentPassport"]["bin"], admin
    )
    logger.info("AgentPassport → %s", addresses["AgentPassport"])

    addresses["AuditTrail"] = provider.deploy(
        artifacts["AuditTrail"]["abi"], artifacts["AuditTrail"]["bin"], admin
    )
    logger.info("AuditTrail → %s", addresses["AuditTrail"])

    addresses["ProofOfWork"] = provider.deploy(
        artifacts["ProofOfWork"]["abi"],
        artifacts["ProofOfWork"]["bin"],
        admin,
        addresses["AgentPassport"],
    )
    logger.info("ProofOfWork → %s", addresses["ProofOfWork"])

    addresses["ReputationRegistry"] = provider.deploy(
        artifacts["ReputationRegistry"]["abi"], artifacts["ReputationRegistry"]["bin"], admin
    )
    logger.info("ReputationRegistry → %s", addresses["ReputationRegistry"])

    # ProofOfWork must be able to bump passport counters when it records a proof.
    passport = provider.w3.eth.contract(address=addresses["AgentPassport"], abi=passport_abi)
    recorder_role = passport.functions.RECORDER_ROLE().call()
    provider.send(passport.functions.grantRole(recorder_role, addresses["ProofOfWork"]))
    logger.info("Granted RECORDER_ROLE on AgentPassport to ProofOfWork")

    if persist:
        # The contracts are deployed either way — the record is a note about them, not the
        # thing itself. A read-only deployments dir (the container hit exactly this, EACCES
        # under an unprivileged user) must not take the whole chain layer down behind a
        # health check that stays green.
        try:
            block = provider.w3.eth.block_number
            registry.save(provider.chain_id, addresses, deployer=admin, block=block)
        except OSError as e:
            logger.warning("Deployed, but could not write the deployment record: %s", e)

    return addresses
