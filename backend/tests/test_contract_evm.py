"""PassportAnchor and Web3AnchorChain on a real EVM (eth-tester running py-evm), not a mock.

The committed artifact (assets/PassportAnchor.json) is deployed to an in-memory chain, so these
tests run the same bytecode that is live on Polygon Amoy. They cover what the mocked chain
tests cannot: access control, the one-time slot, the event, and the real transaction path
(nonce, gas, signing, receipt, log lookup)."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from eth_account import Account
from eth_tester import EthereumTester, PyEVMBackend
from eth_tester.exceptions import TransactionFailed
from eth_typing import HexStr
from web3 import Web3
from web3.providers.eth_tester import EthereumTesterProvider
from web3.types import Wei

import passport_api.chain as chain_mod
from passport_api.chain import Web3AnchorChain, encode_anchor_call

ARTIFACT = json.loads(
    (Path(__file__).resolve().parents[1] / "assets" / "PassportAnchor.json").read_text()
)
CONTENT = bytes.fromhex("11" * 32)
VERIFICATION = bytes.fromhex("22" * 32)
NOT_ISSUER = "0x54ec5063"  # first 4 bytes of keccak("NotIssuer()")
ALREADY_ANCHORED = "0xa0094ce3"  # first 4 bytes of keccak("AlreadyAnchored()")


def selector(signature: str) -> str:
    return Web3.keccak(text=signature)[:4].to_0x_hex()


def reverted_with(error: BaseException, custom_error: str) -> bool:
    """True when a refused call carries this custom error's four byte selector."""
    return repr(bytes.fromhex(custom_error.removeprefix("0x"))) in str(error)


@pytest.fixture
def evm() -> Iterator[tuple[Web3, Any]]:
    tester = EthereumTester(PyEVMBackend())
    w3 = Web3(EthereumTesterProvider(tester))
    yield w3, tester


@pytest.fixture
def deployed(evm: tuple[Web3, Any]) -> tuple[Web3, Any, str]:
    w3, _ = evm
    issuer = list(w3.eth.accounts)[0]
    factory = w3.eth.contract(abi=ARTIFACT["abi"], bytecode=ARTIFACT["bytecode"])
    receipt = w3.eth.wait_for_transaction_receipt(factory.constructor().transact({"from": issuer}))
    contract = w3.eth.contract(address=receipt["contractAddress"], abi=ARTIFACT["abi"])
    return w3, contract, issuer


def test_error_selectors_in_these_tests_match_the_abi() -> None:
    assert selector("NotIssuer()") == NOT_ISSUER
    assert selector("AlreadyAnchored()") == ALREADY_ANCHORED


# -- the contract itself -----------------------------------------------------------------


def test_the_deployer_is_the_issuer(deployed: tuple[Web3, Any, str]) -> None:
    _, contract, issuer = deployed
    assert contract.functions.issuer().call() == issuer


def test_the_issuer_can_anchor_and_the_slot_holds_the_content_hash(
    deployed: tuple[Web3, Any, str],
) -> None:
    w3, contract, issuer = deployed
    assert contract.functions.anchors(VERIFICATION).call() == b"\x00" * 32
    receipt = w3.eth.wait_for_transaction_receipt(
        contract.functions.anchor(CONTENT, VERIFICATION).transact({"from": issuer})
    )
    assert receipt["status"] == 1
    assert contract.functions.anchors(VERIFICATION).call() == CONTENT


def test_anchoring_emits_one_event_with_both_hashes_indexed(
    deployed: tuple[Web3, Any, str],
) -> None:
    w3, contract, issuer = deployed
    receipt = w3.eth.wait_for_transaction_receipt(
        contract.functions.anchor(CONTENT, VERIFICATION).transact({"from": issuer})
    )
    (log,) = contract.events.Anchored().process_receipt(receipt)
    assert log["args"]["contentHash"] == CONTENT
    assert log["args"]["verificationIdHash"] == VERIFICATION


def test_nobody_but_the_issuer_can_anchor(deployed: tuple[Web3, Any, str]) -> None:
    w3, contract, _ = deployed
    stranger = list(w3.eth.accounts)[1]
    with pytest.raises(TransactionFailed) as caught:
        contract.functions.anchor(CONTENT, VERIFICATION).call({"from": stranger})
    assert reverted_with(caught.value, NOT_ISSUER)
    assert contract.functions.anchors(VERIFICATION).call() == b"\x00" * 32


def test_a_slot_can_be_written_only_once(deployed: tuple[Web3, Any, str]) -> None:
    w3, contract, issuer = deployed
    w3.eth.wait_for_transaction_receipt(
        contract.functions.anchor(CONTENT, VERIFICATION).transact({"from": issuer})
    )
    other_content = bytes.fromhex("33" * 32)
    with pytest.raises(TransactionFailed) as caught:
        contract.functions.anchor(other_content, VERIFICATION).call({"from": issuer})
    assert reverted_with(caught.value, ALREADY_ANCHORED)
    assert contract.functions.anchors(VERIFICATION).call() == CONTENT


def test_different_verification_ids_do_not_collide(deployed: tuple[Web3, Any, str]) -> None:
    w3, contract, issuer = deployed
    second = bytes.fromhex("44" * 32)
    for verification, content in ((VERIFICATION, CONTENT), (second, CONTENT)):
        w3.eth.wait_for_transaction_receipt(
            contract.functions.anchor(content, verification).transact({"from": issuer})
        )
    assert contract.functions.anchors(second).call() == CONTENT


def test_the_calldata_the_backend_builds_is_what_the_contract_accepts(
    deployed: tuple[Web3, Any, str],
) -> None:
    w3, contract, issuer = deployed
    data = encode_anchor_call("0x" + CONTENT.hex(), "0x" + VERIFICATION.hex())
    receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.send_transaction(
            {"from": issuer, "to": contract.address, "data": HexStr("0x" + data.hex())}
        )
    )
    assert receipt["status"] == 1
    assert contract.functions.anchors(VERIFICATION).call() == CONTENT


def test_a_large_batch_of_anchors_costs_a_flat_amount_each(
    deployed: tuple[Web3, Any, str],
) -> None:
    w3, contract, issuer = deployed
    gas = []
    for number in range(1, 6):
        verification = number.to_bytes(32, "big")
        receipt = w3.eth.wait_for_transaction_receipt(
            contract.functions.anchor(CONTENT, verification).transact({"from": issuer})
        )
        gas.append(receipt["gasUsed"])
    assert max(gas) - min(gas) == 0
    assert max(gas) < 100_000


# -- Web3AnchorChain on the same EVM -----------------------------------------------------


@pytest.fixture
def chain(
    deployed: tuple[Web3, Any, str], monkeypatch: pytest.MonkeyPatch
) -> tuple[Web3AnchorChain, Web3, Any]:
    """The real chain class, pointed at the in-memory EVM, signing as the deployer."""
    w3, contract, _ = deployed
    key = "0x" + "11" * 32
    account = Account.from_key(key)
    # Pay for a few transactions, then deploy again so the key we hold is the contract's issuer.
    w3.eth.wait_for_transaction_receipt(
        w3.eth.send_transaction(
            {"from": list(w3.eth.accounts)[0], "to": account.address, "value": Wei(10**18)}
        )
    )
    factory = w3.eth.contract(abi=ARTIFACT["abi"], bytecode=ARTIFACT["bytecode"])
    signed = account.sign_transaction(
        factory.constructor().build_transaction(
            {
                "from": account.address,
                "nonce": 0,
                "gasPrice": w3.eth.gas_price,
                "chainId": w3.eth.chain_id,
            }
        )
    )
    receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.send_raw_transaction(signed.raw_transaction)
    )
    address = str(receipt["contractAddress"])
    monkeypatch.setattr(chain_mod, "AMOY_CHAIN_ID", w3.eth.chain_id)
    real = Web3AnchorChain("http://localhost:1", address, key)
    real._w3 = w3
    real._contract = cast(Any, w3.eth.contract(address=cast(Any, address), abi=ARTIFACT["abi"]))
    return real, w3, address


def test_the_chain_class_sees_the_issuer_chain_id_and_nonce(
    chain: tuple[Web3AnchorChain, Web3, Any],
) -> None:
    real, w3, _ = chain
    assert real.sender_address() == real.issuer_address()
    assert real.chain_id() == w3.eth.chain_id
    assert real.pending_nonce() == real.latest_nonce() == 1


def test_a_signed_anchor_goes_through_nonce_gas_and_receipt(
    chain: tuple[Web3AnchorChain, Web3, Any],
) -> None:
    real, _, _ = chain
    data = encode_anchor_call("0x" + CONTENT.hex(), "0x" + VERIFICATION.hex())
    assert real.stored_content(VERIFICATION) == b"\x00" * 32
    sent = real.send_anchor(data, nonce=real.pending_nonce())
    assert real.tx_state(sent.tx_hash) == "success"
    assert real.stored_content(VERIFICATION) == CONTENT
    assert real.pending_nonce() == 2


def test_the_log_lookup_finds_the_transaction_that_anchored_a_pair(
    chain: tuple[Web3AnchorChain, Web3, Any],
) -> None:
    real, _, _ = chain
    data = encode_anchor_call("0x" + CONTENT.hex(), "0x" + VERIFICATION.hex())
    sent = real.send_anchor(data, nonce=real.pending_nonce())
    assert real.find_anchor_tx(CONTENT, VERIFICATION) == sent.tx_hash
    assert real.find_anchor_tx(CONTENT, bytes.fromhex("99" * 32)) is None


def test_an_unknown_transaction_is_missing(chain: tuple[Web3AnchorChain, Web3, Any]) -> None:
    real, _, _ = chain
    assert real.tx_state("0x" + "ab" * 32) == "missing"


def test_a_second_anchor_for_the_same_slot_never_reaches_the_chain(
    chain: tuple[Web3AnchorChain, Web3, Any],
) -> None:
    real, _, _ = chain
    data = encode_anchor_call("0x" + CONTENT.hex(), "0x" + VERIFICATION.hex())
    real.send_anchor(data, nonce=real.pending_nonce())
    again = encode_anchor_call("0x" + ("33" * 32), "0x" + VERIFICATION.hex())
    # The gas estimate runs the call first, and the contract refuses it, so nothing is signed.
    with pytest.raises(TransactionFailed) as caught:
        real.send_anchor(again, nonce=real.pending_nonce())
    assert reverted_with(caught.value, ALREADY_ANCHORED)
    assert real.stored_content(VERIFICATION) == CONTENT


def test_a_wallet_that_is_not_the_issuer_cannot_anchor(
    chain: tuple[Web3AnchorChain, Web3, Any],
) -> None:
    real, w3, address = chain
    stranger_key = "0x" + "22" * 32
    stranger = Web3AnchorChain("http://localhost:1", address, stranger_key)
    stranger._w3 = w3
    stranger._contract = cast(Any, w3.eth.contract(address=cast(Any, address), abi=ARTIFACT["abi"]))
    w3.eth.wait_for_transaction_receipt(
        w3.eth.send_transaction(
            {
                "from": list(w3.eth.accounts)[0],
                "to": stranger.sender_address(),
                "value": Wei(10**18),
            }
        )
    )
    assert chain_mod.can_send(stranger) == "wrong_sender"
    assert chain_mod.can_send(real) is None
    data = encode_anchor_call("0x" + CONTENT.hex(), "0x" + VERIFICATION.hex())
    with pytest.raises(TransactionFailed) as caught:
        stranger.send_anchor(data, nonce=stranger.pending_nonce())
    assert reverted_with(caught.value, NOT_ISSUER)
