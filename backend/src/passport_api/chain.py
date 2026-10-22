import json
from pathlib import Path
from typing import Any, Protocol, cast

from eth_account import Account
from eth_typing import HexStr
from web3 import Web3
from web3.exceptions import TransactionNotFound

from passport_api.settings import settings

AMOY_CHAIN_ID = 80002
_EXPLORER = "https://amoy.polygonscan.com/tx/"
_ARTIFACT = Path(__file__).resolve().parents[2] / "assets" / "PassportAnchor.json"
_ZERO = bytes(32)


class AnchorChain(Protocol):
    def chain_id(self) -> int: ...

    def issuer_address(self) -> str: ...

    def sender_address(self) -> str: ...

    def stored_content(self, verification_id_hash: bytes) -> bytes: ...

    def send_anchor(self, data: bytes) -> str: ...

    def receipt_succeeded(self, tx_hash: str) -> bool | None: ...


class Anchorable(Protocol):
    content_hash: str
    verification_id_hash: str
    anchor_status: str
    tx_hash: str | None
    anchored_at: str | None


def tx_url(tx_hash: str) -> str:
    return f"{_EXPLORER}{tx_hash}"


def publish_anchor(version: Anchorable, chain: AnchorChain, *, now: str) -> None:
    if version.anchor_status == "confirmed":
        return
    if not _can_send(chain):
        version.anchor_status = "failed"
        return
    if version.tx_hash:
        if _apply_receipt(version, chain, version.tx_hash, now):
            return
        version.anchor_status = "failed"
        version.anchored_at = None
    verification = _bytes32(version.verification_id_hash)
    if chain.stored_content(verification) != _ZERO:
        return
    try:
        tx_hash = chain.send_anchor(
            encode_anchor_call(version.content_hash, version.verification_id_hash)
        )
    except Exception:
        version.anchor_status = "failed"
        version.anchored_at = None
        return
    version.tx_hash = tx_hash
    if not _apply_receipt(version, chain, tx_hash, now):
        version.anchor_status = "failed"
        version.anchored_at = None


def encode_anchor_call(content_hash: str, verification_id_hash: str) -> bytes:
    contract = Web3().eth.contract(abi=_abi())
    encoded = contract.encode_abi(
        "anchor",
        args=[_bytes32(content_hash), _bytes32(verification_id_hash)],
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

    def send_anchor(self, data: bytes) -> str:
        txn: dict[str, Any] = {
            "from": self._account.address,
            "to": self._contract.address,
            "data": "0x" + data.hex(),
            "nonce": self._w3.eth.get_transaction_count(self._account.address),
            "chainId": AMOY_CHAIN_ID,
        }
        txn["gas"] = self._w3.eth.estimate_gas(cast(Any, txn))
        txn["gasPrice"] = self._w3.eth.gas_price
        signed = self._account.sign_transaction(cast(Any, txn))
        sent = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        return str(sent.to_0x_hex())

    def receipt_succeeded(self, tx_hash: str) -> bool | None:
        try:
            receipt = self._w3.eth.get_transaction_receipt(HexStr(tx_hash))
        except TransactionNotFound:
            return None
        return bool(receipt["status"])


def _can_send(chain: AnchorChain) -> bool:
    return (
        chain.chain_id() == AMOY_CHAIN_ID
        and chain.sender_address().lower() == chain.issuer_address().lower()
    )


def _apply_receipt(version: Anchorable, chain: AnchorChain, tx_hash: str, now: str) -> bool:
    receipt = chain.receipt_succeeded(tx_hash)
    if receipt is None:
        version.anchor_status = "pending"
        version.anchored_at = None
        return True
    if receipt:
        version.anchor_status = "confirmed"
        version.anchored_at = now
        return True
    return False


def _abi() -> list[dict[str, Any]]:
    payload = json.loads(_ARTIFACT.read_text())
    abi = payload["abi"]
    if not isinstance(abi, list):
        raise RuntimeError("anchor_abi_missing")
    return [cast(dict[str, Any], item) for item in abi if isinstance(item, dict)]


def _bytes32(value: str) -> bytes:
    raw = bytes.fromhex(value.removeprefix("0x"))
    if len(raw) != 32:
        raise RuntimeError("bytes32")
    return raw
