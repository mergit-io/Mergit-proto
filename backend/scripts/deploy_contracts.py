"""Deploy the Mergit contract set.

    # local in-process EVM (no keys, no tokens, no network)
    .venv/bin/python scripts/deploy_contracts.py --network local

    # Monad testnet — needs CHAIN_RPC_URL + a funded CHAIN_PRIVATE_KEY
    .venv/bin/python scripts/deploy_contracts.py --network monad-testnet
    .venv/bin/python scripts/deploy_contracts.py --network monad-testnet --dry-run

Writes contract addresses to backend/deployments/{chainId}.json.
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chain import compiler, deployer, networks, registry  # noqa: E402
from chain.provider import build_provider  # noqa: E402
from config import settings  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy Mergit contracts")
    parser.add_argument("--network", default=settings.chain_target,
                        choices=sorted(networks.NETWORKS), help="chain target")
    parser.add_argument("--rpc-url", default=settings.chain_rpc_url)
    parser.add_argument("--private-key", default=settings.chain_private_key)
    parser.add_argument("--dry-run", action="store_true",
                        help="compile and report, deploy nothing")
    args = parser.parse_args()

    network = networks.get_network(args.network)
    print(f"\n── Mergit contract deployment ──")
    print(f"target   : {network.name} (chainId {network.chain_id})")

    artifacts = compiler.compile_all()
    print(f"compiled : {len(artifacts)} contracts with solc {compiler.SOLC_VERSION}")
    for name, art in sorted(artifacts.items()):
        print(f"           {name:<20} {len(art['bin']) // 2:>6} bytes")

    if args.dry_run:
        print("\ndry run — nothing deployed.")
        if not network.is_local:
            have_rpc = bool(args.rpc_url or network.rpc_url)
            have_key = bool(args.private_key)
            print(f"  RPC URL     : {'set' if have_rpc else 'MISSING (set CHAIN_RPC_URL)'}")
            print(f"  private key : {'set' if have_key else 'MISSING (set CHAIN_PRIVATE_KEY)'}")
            if not have_key and network.faucets:
                print("  fund the deployer address from any of:")
                for f in network.faucets:
                    print(f"    - {f}")
        return 0

    if not network.is_local and not args.private_key:
        print("\nERROR: deploying to a live network needs CHAIN_PRIVATE_KEY.", file=sys.stderr)
        print("Run with --dry-run to see what would happen, or use --network local.",
              file=sys.stderr)
        return 1

    try:
        provider = build_provider(args.network, args.rpc_url, args.private_key)
    except Exception as e:
        print(f"\nERROR: could not connect to {network.name}: {e}", file=sys.stderr)
        return 1

    print(f"deployer : {provider.sender_address}")
    if not network.is_local:
        balance = provider.w3.eth.get_balance(provider.sender_address)
        print(f"balance  : {provider.w3.from_wei(balance, 'ether')} {network.currency}")
        if balance == 0:
            print(f"\nERROR: deployer has no {network.currency}.", file=sys.stderr)
            for f in network.faucets:
                print(f"  faucet: {f}", file=sys.stderr)
            return 1

    print("\ndeploying…")
    addresses = deployer.deploy_all(provider, persist=True)

    print("\n── Deployed ──")
    for name, address in addresses.items():
        url = network.address_url(address)
        print(f"  {name:<20} {address}" + (f"\n  {'':<20} {url}" if url else ""))

    print(f"\nwrote {registry.path_for(network.chain_id)}")
    if network.is_local:
        print("\nNote: the local EVM is in-process — these addresses live only for this run.\n"
              "The backend redeploys automatically on startup when CHAIN_TARGET=local.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
