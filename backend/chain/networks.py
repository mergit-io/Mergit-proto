"""Chain target registry.

Adding a network is a data change, not a code change — the client, deployer and API all
read from here. Monad testnet is the product target; `local` is an in-process EVM so the
whole pipeline runs with no keys, no tokens and no network.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Network:
    key: str
    name: str
    chain_id: int
    rpc_url: str = ""
    explorer_base: str = ""
    currency: str = "ETH"
    is_local: bool = False
    faucets: tuple[str, ...] = ()

    def tx_url(self, tx_hash: str) -> str | None:
        if not self.explorer_base:
            return None
        return f"{self.explorer_base}/tx/{tx_hash}"

    def address_url(self, address: str) -> str | None:
        if not self.explorer_base:
            return None
        return f"{self.explorer_base}/address/{address}"

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "chainId": self.chain_id,
            "explorer": self.explorer_base or None,
            "currency": self.currency,
            "isLocal": self.is_local,
        }


LOCAL = Network(
    key="local",
    name="Local EVM (py-evm)",
    chain_id=31337,
    currency="ETH",
    is_local=True,
)

MONAD_TESTNET = Network(
    key="monad-testnet",
    name="Monad Testnet",
    chain_id=10143,
    rpc_url="https://testnet-rpc.monad.xyz",
    explorer_base="https://testnet.monadexplorer.com",
    currency="MON",
    faucets=(
        "https://faucet.monad.xyz",              # 10 MON/24h, needs >=0.001 ETH on mainnet
        "https://chainstack.com/monad-faucet",   # 0.5 MON/24h, no gate
        "https://faucet.quicknode.com/monad",
        "https://www.alchemy.com/faucets/monad-testnet",
    ),
)

NETWORKS: dict[str, Network] = {n.key: n for n in (LOCAL, MONAD_TESTNET)}

DEFAULT_NETWORK_KEY = "local"


def get_network(key: str) -> Network:
    try:
        return NETWORKS[key]
    except KeyError:
        raise KeyError(
            f"Unknown chain target {key!r}; known: {', '.join(sorted(NETWORKS))}"
        ) from None


def by_chain_id(chain_id: int) -> Network | None:
    return next((n for n in NETWORKS.values() if n.chain_id == chain_id), None)
