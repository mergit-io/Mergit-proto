"""Transaction providers — one interface, two backends.

`LocalEvmProvider` runs a real EVM in-process (py-evm): real bytecode, real receipts,
real event logs, instant blocks, pre-funded accounts, zero setup.

`RpcProvider` talks to a real node over JSON-RPC with local key signing. The contract
code and the calling code are identical in both cases; only the transport differs.
"""
import logging
import time
from typing import Any

from eth_account import Account
from web3 import EthereumTesterProvider, HTTPProvider, Web3
from web3.exceptions import ContractLogicError

from . import networks

logger = logging.getLogger(__name__)

_RECEIPT_TIMEOUT = 180
_MAX_SEND_ATTEMPTS = 3


class ChainSendError(RuntimeError):
    """A transaction could not be landed. Carries the revert reason when there is one."""

    def __init__(self, message: str, revert_reason: str | None = None):
        super().__init__(message)
        self.revert_reason = revert_reason


def hex0x(value) -> str:
    """Normalize HexBytes/bytes/str to a 0x-prefixed hex string.

    hexbytes>=1.0 dropped the 0x prefix from .hex(), so this must not be assumed.
    """
    if isinstance(value, (bytes, bytearray)):
        raw = value.hex()
    else:
        raw = str(value)
    return raw if raw.startswith("0x") else "0x" + raw


def _revert_reason(exc: Exception) -> str | None:
    text = str(exc)
    for marker in ("execution reverted:", "revert"):
        if marker in text.lower():
            return text[:400]
    return None


class LocalEvmProvider:
    """In-process EVM. Every instance is a fresh chain."""

    def __init__(self, network: networks.Network = networks.LOCAL):
        self.network = network
        self.w3 = Web3(EthereumTesterProvider())
        self.sender_address = self.w3.eth.accounts[0]

    @property
    def chain_id(self) -> int:
        return self.network.chain_id

    def send(self, fn_call: Any) -> dict:
        # Simulate first so a revert surfaces as a clean error rather than a burnt tx.
        try:
            fn_call.call({"from": self.sender_address})
        except (ContractLogicError, Exception) as e:  # noqa: B014 - eth-tester raises broadly
            raise ChainSendError(f"call reverted: {e}", _revert_reason(e)) from e

        tx_hash = fn_call.transact({"from": self.sender_address})
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status != 1:
            raise ChainSendError("transaction reverted on chain")
        return self._normalize(receipt)

    def deploy(self, abi: list, bytecode: str, *args) -> str:
        factory = self.w3.eth.contract(abi=abi, bytecode=bytecode)
        tx_hash = factory.constructor(*args).transact({"from": self.sender_address})
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status != 1:
            raise ChainSendError("contract deployment reverted")
        return receipt.contractAddress

    def _normalize(self, receipt) -> dict:
        return {
            "tx_hash": hex0x(receipt.transactionHash),
            "block_number": receipt.blockNumber,
            "gas_used": receipt.gasUsed,
            "raw": receipt,
        }


class RpcProvider:
    """Real node over JSON-RPC, signing locally with a private key."""

    def __init__(self, network: networks.Network, rpc_url: str, private_key: str):
        if not rpc_url:
            raise ValueError(f"{network.key}: no RPC URL configured")
        if not private_key:
            raise ValueError(f"{network.key}: no private key configured")

        self.network = network
        self.w3 = Web3(HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        self.account = Account.from_key(private_key)
        self.sender_address = self.account.address

    @property
    def chain_id(self) -> int:
        return self.network.chain_id

    def _build(self, fn_call) -> dict:
        tx = {
            "from": self.sender_address,
            "nonce": self.w3.eth.get_transaction_count(self.sender_address, "pending"),
            "chainId": self.network.chain_id,
        }
        try:  # EIP-1559 where supported, legacy otherwise
            base = self.w3.eth.get_block("latest").get("baseFeePerGas")
            if base:
                priority = self.w3.eth.max_priority_fee
                tx["maxPriorityFeePerGas"] = priority
                tx["maxFeePerGas"] = base * 2 + priority
            else:
                tx["gasPrice"] = self.w3.eth.gas_price
        except Exception:
            tx["gasPrice"] = self.w3.eth.gas_price

        built = fn_call.build_transaction(tx)
        if "gas" not in built:
            built["gas"] = int(fn_call.estimate_gas({"from": self.sender_address}) * 1.25)
        return built

    def send(self, fn_call: Any) -> dict:
        try:
            fn_call.call({"from": self.sender_address})
        except Exception as e:
            raise ChainSendError(f"call reverted: {e}", _revert_reason(e)) from e

        last: Exception | None = None
        for attempt in range(1, _MAX_SEND_ATTEMPTS + 1):
            try:
                signed = self.account.sign_transaction(self._build(fn_call))
                tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
                receipt = self.w3.eth.wait_for_transaction_receipt(
                    tx_hash, timeout=_RECEIPT_TIMEOUT
                )
                if receipt.status != 1:
                    raise ChainSendError("transaction reverted on chain")
                return {
                    "tx_hash": hex0x(receipt.transactionHash),
                    "block_number": receipt.blockNumber,
                    "gas_used": receipt.gasUsed,
                    "raw": receipt,
                }
            except ChainSendError:
                raise
            except Exception as e:
                last = e
                logger.warning(
                    "chain send attempt %d/%d failed: %s", attempt, _MAX_SEND_ATTEMPTS, e
                )
                if attempt < _MAX_SEND_ATTEMPTS:
                    time.sleep(2**attempt)
        raise ChainSendError(f"send failed after {_MAX_SEND_ATTEMPTS} attempts: {last}")

    def deploy(self, abi: list, bytecode: str, *args) -> str:
        factory = self.w3.eth.contract(abi=abi, bytecode=bytecode)
        built = factory.constructor(*args).build_transaction({
            "from": self.sender_address,
            "nonce": self.w3.eth.get_transaction_count(self.sender_address, "pending"),
            "chainId": self.network.chain_id,
            "gasPrice": self.w3.eth.gas_price,
        })
        signed = self.account.sign_transaction(built)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=_RECEIPT_TIMEOUT)
        if receipt.status != 1:
            raise ChainSendError("contract deployment reverted")
        return receipt.contractAddress


def build_provider(target: str, rpc_url: str = "", private_key: str = ""):
    """Construct the provider for a chain target key."""
    network = networks.get_network(target)
    if network.is_local:
        return LocalEvmProvider(network)
    return RpcProvider(network, rpc_url or network.rpc_url, private_key)
