import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from eth_account import Account
from eth_typing import HexStr
from web3 import Web3
from web3.exceptions import TransactionNotFound
from web3.middleware import ExtraDataToPOAMiddleware

from passport_api.settings import settings

AMOY_CHAIN_ID = 80002
_EXPLORER = "https://amoy.polygonscan.com/tx/"
_ARTIFACT = Path(__file__).resolve().parents[2] / "assets" / "PassportAnchor.json"
ZERO = bytes(32)


TxState = Literal["success", "reverted", "pending", "missing"]

# A replacement must pay clearly more than the transaction it replaces, or nodes refuse it
# ("replacement transaction underpriced"). Nodes ask for at least 10 percent.
GAS_BUMP_PERCENT = 25
# Refuse to pay more than this per gas unit, whatever the network quotes (500 gwei).
MAX_GAS_PRICE_WEI = 500 * 10**9
# How far back to search the contract's logs for an existing anchor transaction.
_LOG_LOOKBACK_BLOCKS = 100_000
_GAS_LIMIT_MARGIN_PERCENT = 120


@dataclass(frozen=True)
class SentTx:
    tx_hash: str
    nonce: int
    gas_price: int


class AnchorChain(Protocol):
    def chain_id(self) -> int: ...

    def issuer_address(self) -> str: ...

    def sender_address(self) -> str: ...

    def stored_content(self, verification_id_hash: bytes) -> bytes: ...

    def pending_nonce(self) -> int:
        """Next nonce counting transactions still waiting in the mempool."""
        ...

    def latest_nonce(self) -> int:
        """Next nonce counting only mined transactions."""
        ...

    def send_anchor(self, data: bytes, *, nonce: int, min_gas_price: int | None = None) -> SentTx:
        """Sign and broadcast an anchor call with an explicit nonce. Never waits for a block.
        Sending again with the same nonce and a higher gas price replaces the earlier one."""
        ...

    def tx_state(self, tx_hash: str) -> TxState: ...

    def find_anchor_tx(self, content_hash: bytes, verification_id_hash: bytes) -> str | None:
        """Hash of the mined transaction that anchored this pair, when the logs show it."""
        ...


def tx_url(tx_hash: str) -> str:
    return f"{_EXPLORER}{tx_hash}"


def bumped_gas_price(previous: int) -> int:
    """Smallest price a replacement should pay: the previous one plus GAS_BUMP_PERCENT."""
    return previous + max(1, -(-previous * GAS_BUMP_PERCENT // 100))


def can_send(chain: AnchorChain) -> str | None:
    """None when this chain and wallet may anchor, otherwise a short reason."""
    if chain.chain_id() != AMOY_CHAIN_ID:
        return "wrong_chain"
    if chain.sender_address().lower() != chain.issuer_address().lower():
        return "wrong_sender"
    return None


def encode_anchor_call(content_hash: str, verification_id_hash: str) -> bytes:
    contract = Web3().eth.contract(abi=_abi())
    encoded = contract.encode_abi(
        "anchor",
        args=[bytes32(content_hash), bytes32(verification_id_hash)],
    )
    if not isinstance(encoded, str) or not encoded.startswith("0x"):
        raise RuntimeError("anchor_calldata")
    return bytes.fromhex(encoded[2:])


def chain_from_settings() -> AnchorChain | None:
    if not (
        settings.amoy_rpc_url
        and settings.anchor_contract_address
        and settings.btu_issuer_private_key
    ):
        return None
    return Web3AnchorChain(
        settings.amoy_rpc_url,
        settings.anchor_contract_address,
        settings.btu_issuer_private_key,
    )


class Web3AnchorChain:
    def __init__(self, rpc_url: str, contract_address: str, private_key: str) -> None:
        self._w3 = Web3(Web3.HTTPProvider(rpc_url))
        # Polygon is a proof-of-authority chain with long block extraData.
        self._w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self._account = Account.from_key(private_key)
        self._contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=_abi(),
        )

    def chain_id(self) -> int:
        chain_id = self._w3.eth.chain_id
        return int(chain_id)

    def issuer_address(self) -> str:
        issuer = self._contract.functions.issuer().call()
        return str(issuer)

    def sender_address(self) -> str:
        return str(self._account.address)

    def stored_content(self, verification_id_hash: bytes) -> bytes:
        stored = self._contract.functions.anchors(verification_id_hash).call()
        return bytes(stored)

    def pending_nonce(self) -> int:
        return int(self._w3.eth.get_transaction_count(self._account.address, "pending"))

    def latest_nonce(self) -> int:
        return int(self._w3.eth.get_transaction_count(self._account.address, "latest"))

    def send_anchor(self, data: bytes, *, nonce: int, min_gas_price: int | None = None) -> SentTx:
        gas_price = int(self._w3.eth.gas_price)
        if min_gas_price is not None:
            gas_price = max(gas_price, min_gas_price)
        if gas_price > MAX_GAS_PRICE_WEI:
            raise RuntimeError("gas_price_too_high")
        txn: dict[str, Any] = {
            "from": self._account.address,
            "to": self._contract.address,
            "data": "0x" + data.hex(),
            "nonce": nonce,
            "chainId": AMOY_CHAIN_ID,
        }
        estimate = int(self._w3.eth.estimate_gas(cast(Any, txn)))
        txn["gas"] = estimate * _GAS_LIMIT_MARGIN_PERCENT // 100
        txn["gasPrice"] = gas_price
        signed = self._account.sign_transaction(cast(Any, txn))
        sent = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        return SentTx(tx_hash=str(sent.to_0x_hex()), nonce=nonce, gas_price=gas_price)

    def tx_state(self, tx_hash: str) -> TxState:
        try:
            receipt = self._w3.eth.get_transaction_receipt(HexStr(tx_hash))
        except TransactionNotFound:
            receipt = None
        if receipt is not None:
            return "success" if bool(receipt["status"]) else "reverted"
        try:
            self._w3.eth.get_transaction(HexStr(tx_hash))
        except TransactionNotFound:
            return "missing"
        return "pending"

    def find_anchor_tx(self, content_hash: bytes, verification_id_hash: bytes) -> str | None:
        try:
            latest = int(self._w3.eth.block_number)
            logs = self._w3.eth.get_logs(
                cast(
                    Any,
                    {
                        "address": self._contract.address,
                        "fromBlock": max(0, latest - _LOG_LOOKBACK_BLOCKS),
                        "toBlock": latest,
                        "topics": [
                            Web3.keccak(text="Anchored(bytes32,bytes32)").to_0x_hex(),
                            "0x" + content_hash.hex(),
                            "0x" + verification_id_hash.hex(),
                        ],
                    },
                )
            )
        except Exception:
            # Public RPCs often cap the log range. This lookup is best effort.
            return None
        if not logs:
            return None
        return str(logs[0]["transactionHash"].to_0x_hex())


def _abi() -> list[dict[str, Any]]:
    payload = json.loads(_ARTIFACT.read_text())
    abi = payload["abi"]
    if not isinstance(abi, list):
        raise RuntimeError("anchor_abi_missing")
    return [cast(dict[str, Any], item) for item in abi if isinstance(item, dict)]


def bytes32(value: str) -> bytes:
    raw = bytes.fromhex(value.removeprefix("0x"))
    if len(raw) != 32:
        raise RuntimeError("bytes32")
    return raw
