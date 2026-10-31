"""Web3AnchorChain against a mocked web3 connection: nonces, gas, receipts, logs."""

from typing import Any
from unittest.mock import MagicMock

import pytest
from web3 import Web3
from web3.exceptions import TransactionNotFound

from passport_api.chain import (
    GAS_BUMP_PERCENT,
    MAX_GAS_PRICE_WEI,
    Web3AnchorChain,
    bumped_gas_price,
    can_send,
)

KEY = "0x" + "11" * 32
CONTRACT = "0x" + "ab" * 20
CONTENT = bytes.fromhex("11" * 32)
VERIFICATION = bytes.fromhex("22" * 32)
DATA = b"\xaa\xbb\xcc\xdd" + CONTENT + VERIFICATION


class _Hash:
    def __init__(self, value: str) -> None:
        self.value = value

    def to_0x_hex(self) -> str:
        return self.value


def _chain() -> tuple[Web3AnchorChain, MagicMock, dict[str, Any]]:
    chain = Web3AnchorChain("http://localhost:1", CONTRACT, KEY)
    w3 = MagicMock()
    chain._w3 = w3
    signed: dict[str, Any] = {}

    def sign(txn: dict[str, Any]) -> MagicMock:
        signed.update(txn)
        return MagicMock(raw_transaction=b"\x01\x02")

    account = MagicMock()
    account.address = chain.sender_address()
    account.sign_transaction.side_effect = sign
    chain._account = account
    w3.eth.send_raw_transaction.return_value = _Hash("0x" + "ee" * 32)
    w3.eth.gas_price = 30_000_000_000
    w3.eth.estimate_gas.return_value = 50_000
    return chain, w3, signed


def test_nonce_reads_use_the_pending_and_the_latest_block() -> None:
    chain, w3, _ = _chain()
    w3.eth.get_transaction_count.return_value = 9
    assert chain.pending_nonce() == 9
    assert w3.eth.get_transaction_count.call_args.args[1] == "pending"
    assert chain.latest_nonce() == 9
    assert w3.eth.get_transaction_count.call_args.args[1] == "latest"


def test_send_uses_the_given_nonce_and_never_waits_for_a_receipt() -> None:
    chain, w3, signed = _chain()
    sent = chain.send_anchor(DATA, nonce=12)
    assert (sent.tx_hash, sent.nonce, sent.gas_price) == ("0x" + "ee" * 32, 12, 30_000_000_000)
    assert signed["nonce"] == 12
    assert signed["chainId"] == 80002
    assert signed["gasPrice"] == 30_000_000_000
    assert signed["gas"] == 60_000  # estimate plus 20 percent
    assert signed["data"] == "0x" + DATA.hex()
    w3.eth.wait_for_transaction_receipt.assert_not_called()
    w3.eth.get_transaction_count.assert_not_called()


def test_a_replacement_pays_at_least_the_floor_even_if_the_network_is_cheaper() -> None:
    chain, _, signed = _chain()
    floor = bumped_gas_price(30_000_000_000)
    sent = chain.send_anchor(DATA, nonce=3, min_gas_price=floor)
    assert sent.gas_price == floor == signed["gasPrice"]
    assert floor >= 30_000_000_000 * (100 + GAS_BUMP_PERCENT) // 100


def test_the_network_price_wins_when_it_has_risen_above_the_floor() -> None:
    chain, w3, _ = _chain()
    w3.eth.gas_price = 80_000_000_000
    assert (
        chain.send_anchor(DATA, nonce=3, min_gas_price=40_000_000_000).gas_price == 80_000_000_000
    )


def test_a_price_above_the_hard_cap_is_refused_before_signing() -> None:
    chain, w3, signed = _chain()
    w3.eth.gas_price = MAX_GAS_PRICE_WEI + 1
    with pytest.raises(RuntimeError, match="gas_price_too_high"):
        chain.send_anchor(DATA, nonce=1)
    assert signed == {}
    w3.eth.send_raw_transaction.assert_not_called()


def test_bumped_gas_price_always_rises_by_the_bump_and_by_at_least_one() -> None:
    assert bumped_gas_price(1_000_000_000) == 1_250_000_000
    assert bumped_gas_price(1) == 2
    assert bumped_gas_price(7) > 7


def test_tx_state_reads_the_receipt_status() -> None:
    chain, w3, _ = _chain()
    w3.eth.get_transaction_receipt.return_value = {"status": 1}
    assert chain.tx_state("0x" + "aa" * 32) == "success"
    w3.eth.get_transaction_receipt.return_value = {"status": 0}
    assert chain.tx_state("0x" + "aa" * 32) == "reverted"


def test_tx_state_tells_pending_from_missing() -> None:
    chain, w3, _ = _chain()
    w3.eth.get_transaction_receipt.side_effect = TransactionNotFound("no receipt")
    w3.eth.get_transaction.return_value = {"hash": "0xaa"}
    assert chain.tx_state("0x" + "aa" * 32) == "pending"
    w3.eth.get_transaction.side_effect = TransactionNotFound("unknown")
    assert chain.tx_state("0x" + "aa" * 32) == "missing"


def test_a_node_error_while_reading_a_receipt_is_not_hidden() -> None:
    chain, w3, _ = _chain()
    w3.eth.get_transaction_receipt.side_effect = ConnectionError("down")
    with pytest.raises(ConnectionError):
        chain.tx_state("0x" + "aa" * 32)


def test_find_anchor_tx_filters_the_logs_by_both_indexed_hashes() -> None:
    chain, w3, _ = _chain()
    w3.eth.block_number = 500_000
    w3.eth.get_logs.return_value = [{"transactionHash": _Hash("0x" + "cc" * 32)}]
    assert chain.find_anchor_tx(CONTENT, VERIFICATION) == "0x" + "cc" * 32
    query = w3.eth.get_logs.call_args.args[0]
    assert query["address"] == chain._contract.address
    assert query["fromBlock"] == 400_000
    topics = query["topics"]
    assert topics[0] == Web3.keccak(text="Anchored(bytes32,bytes32)").to_0x_hex()
    assert topics[1] == "0x" + CONTENT.hex()
    assert topics[2] == "0x" + VERIFICATION.hex()


def test_find_anchor_tx_gives_up_quietly() -> None:
    chain, w3, _ = _chain()
    w3.eth.block_number = 10
    w3.eth.get_logs.return_value = []
    assert chain.find_anchor_tx(CONTENT, VERIFICATION) is None
    assert w3.eth.get_logs.call_args.args[0]["fromBlock"] == 0
    w3.eth.get_logs.side_effect = ValueError({"message": "block range too large"})
    assert chain.find_anchor_tx(CONTENT, VERIFICATION) is None


def test_can_send_names_the_problem() -> None:
    chain, w3, _ = _chain()
    w3.eth.chain_id = 1
    assert can_send(chain) == "wrong_chain"
    w3.eth.chain_id = 80002
    chain._contract = MagicMock()
    chain._contract.functions.issuer.return_value.call.return_value = "0x" + "99" * 20
    assert can_send(chain) == "wrong_sender"
    chain._contract.functions.issuer.return_value.call.return_value = chain.sender_address()
    assert can_send(chain) is None
