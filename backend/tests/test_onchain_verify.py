"""Public verify against the chain: recompute the hash, read the contract, compare."""

import importlib.util
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from web3.exceptions import TransactionNotFound

import passport_api.onchain as onchain
from passport_api.chain import ZERO, bytes32, contract_abi
from passport_api.demo_data import DEMO_VERSIONS
from passport_api.fingerprint import verification_id_hash
from passport_api.main import app
from passport_api.onchain import (
    FILLED_TTL_SECONDS,
    OUTAGE_BACKOFF_SECONDS,
    OnchainVerifier,
    Web3AnchorReader,
    contract_url,
    verifier_from_settings,
)
from passport_api.schemas import Skill
from passport_api.settings import settings
from passport_api.store import MemoryStore, StoredVersion
from passport_api.verify import (
    VerifyFound,
    VerifyOutdated,
    VerifyPending,
    VerifyRevoked,
    VerifyTampered,
    verify_code,
)

CURRENT = DEMO_VERSIONS[1]
OLDER = DEMO_VERSIONS[0]
PENDING = DEMO_VERSIONS[2]
CODE = CURRENT.verification_code
CODE_HASH = bytes32(verification_id_hash(CODE))
GOOD = bytes32(CURRENT.content_hash or "")
OTHER = bytes.fromhex("ab" * 32)


class FakeReader:
    """A scripted contract: slots by verification id hash, a call counter and an outage switch."""

    def __init__(self, slots: dict[bytes, bytes] | None = None, block: int | None = 4242) -> None:
        self.slots = slots if slots is not None else {CODE_HASH: GOOD}
        self.block = block
        self.reads = 0
        self.block_lookups = 0
        self.down = False

    def read_anchor(self, verification_id_hash: bytes) -> bytes:
        self.reads += 1
        if self.down:
            raise TimeoutError("rpc timeout")
        return self.slots.get(verification_id_hash, ZERO)

    def block_of(self, tx_hash: str) -> int | None:
        self.block_lookups += 1
        if self.down:
            raise TimeoutError("rpc timeout")
        return self.block


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _verifier(reader: FakeReader, clock: Clock | None = None) -> OnchainVerifier:
    return OnchainVerifier(reader, clock=clock or Clock())


def _store(*versions: StoredVersion) -> MemoryStore:
    return MemoryStore(list(versions))


# --- outcomes -------------------------------------------------------------------------


def test_matching_hash_on_chain_is_valid_and_verified_with_block_and_links() -> None:
    result = verify_code(MemoryStore(DEMO_VERSIONS), CODE, _verifier(FakeReader()))
    assert isinstance(result, VerifyFound)
    assert result.outcome == "valid"
    assert result.onchain.status == "verified"
    assert result.onchain.block_number == 4242
    assert result.onchain.content_hash == CURRENT.content_hash
    assert result.onchain.verification_id_hash == verification_id_hash(CODE)
    assert result.onchain.contract_url == contract_url()
    assert result.tx_url.endswith(CURRENT.tx_hash or "?")


def test_outdated_version_is_checked_on_chain_too() -> None:
    older_hash = bytes32(verification_id_hash(OLDER.verification_code))
    reader = FakeReader({older_hash: bytes32(OLDER.content_hash or "")})
    result = verify_code(MemoryStore(DEMO_VERSIONS), OLDER.verification_code, _verifier(reader))
    assert isinstance(result, VerifyOutdated)
    assert result.onchain.status == "verified"


def test_different_hash_on_chain_is_tampered_with_no_name_or_skills() -> None:
    reader = FakeReader({CODE_HASH: OTHER})
    result = verify_code(MemoryStore(DEMO_VERSIONS), CODE, _verifier(reader))
    assert isinstance(result, VerifyTampered)
    assert result.model_dump() == {
        "outcome": "tampered",
        "reason": "chain_mismatch",
        "contract_url": contract_url(),
    }
    assert CURRENT.holder_name not in result.model_dump_json()
    assert "skills" not in result.model_dump()


def test_empty_slot_for_a_confirmed_version_is_tampered() -> None:
    result = verify_code(MemoryStore(DEMO_VERSIONS), CODE, _verifier(FakeReader({})))
    assert isinstance(result, VerifyTampered)
    assert result.reason == "not_on_chain"


def test_empty_slot_right_after_confirmation_is_unavailable_not_tampered() -> None:
    fresh = datetime.now(UTC) - timedelta(seconds=20)
    version = replace(CURRENT, anchored_at=fresh.isoformat())
    result = verify_code(_store(version), CODE, _verifier(FakeReader({})))
    assert isinstance(result, VerifyFound)
    assert result.onchain.status == "unavailable"


def test_empty_slot_long_after_confirmation_is_tampered() -> None:
    old = datetime.now(UTC) - timedelta(hours=2)
    version = replace(CURRENT, anchored_at=old.isoformat().replace("+00:00", "Z"))
    result = verify_code(_store(version), CODE, _verifier(FakeReader({})))
    assert isinstance(result, VerifyTampered)


@pytest.mark.parametrize(
    "change",
    [
        {"holder_name": "Someone Else"},
        {"skills": (Skill(skill="Python", badge="Foundation", awarded_on="2025-01-15"),)},
        {"passport_id": "BTU-ZZZZZZZZZZ"},
        {"version": 7},
    ],
)
def test_database_edit_is_tampered_even_if_the_chain_is_fine(change: dict[str, object]) -> None:
    edited = replace(CURRENT, **change)  # type: ignore[arg-type]
    reader = FakeReader()
    result = verify_code(_store(edited), CODE, _verifier(reader))
    assert isinstance(result, VerifyTampered)
    assert result.reason == "stored_content_changed"
    assert result.model_dump().keys() == {"outcome", "reason", "contract_url"}
    # The database check fails first, so the chain is not even asked.
    assert reader.reads == 0


def test_database_content_hash_edited_to_match_a_forged_passport_is_still_caught() -> None:
    """An attacker changes the name and recomputes the DB hash: the chain disagrees."""
    from passport_api.fingerprint import content_hash

    forged_name = "Forged Name"
    forged_hash = content_hash(
        holder_name=forged_name,
        passport_id=CURRENT.passport_id,
        skills=CURRENT.skills,
        version=CURRENT.version,
    )
    forged = replace(CURRENT, holder_name=forged_name, content_hash=forged_hash)
    result = verify_code(_store(forged), CODE, _verifier(FakeReader()))
    assert isinstance(result, VerifyTampered)
    assert result.reason == "chain_mismatch"


def test_rpc_unreachable_still_shows_the_database_result_but_never_verified() -> None:
    reader = FakeReader()
    reader.down = True
    result = verify_code(MemoryStore(DEMO_VERSIONS), CODE, _verifier(reader))
    assert isinstance(result, VerifyFound)
    assert result.outcome == "valid"
    assert result.holder_name == CURRENT.holder_name
    assert result.onchain.status == "unavailable"
    assert result.onchain.block_number is None


def test_no_verifier_means_unavailable_never_verified() -> None:
    result = verify_code(MemoryStore(DEMO_VERSIONS), CODE, None)
    assert isinstance(result, VerifyFound)
    assert result.onchain.status == "unavailable"


def test_a_crashing_verifier_does_not_break_verify() -> None:
    broken = MagicMock()
    broken.check.side_effect = RuntimeError("boom")
    result = verify_code(MemoryStore(DEMO_VERSIONS), CODE, broken)
    assert isinstance(result, VerifyFound)
    assert result.onchain.status == "unavailable"


def test_block_lookup_failure_still_verifies_without_a_block() -> None:
    reader = FakeReader(block=None)
    result = verify_code(MemoryStore(DEMO_VERSIONS), CODE, _verifier(reader))
    assert isinstance(result, VerifyFound)
    assert result.onchain.status == "verified"
    assert result.onchain.block_number is None


def test_confirmed_without_a_stored_hash_is_an_error() -> None:
    broken = replace(CURRENT, content_hash=None)
    assert verify_code(_store(broken), CODE, _verifier(FakeReader())).model_dump() == {
        "outcome": "error"
    }


def test_revoked_and_pending_do_not_touch_the_chain() -> None:
    reader = FakeReader()
    revoked = replace(CURRENT, version_revoked_at="2026-10-30T10:00:00+00:00")
    assert isinstance(verify_code(_store(revoked), CODE, _verifier(reader)), VerifyRevoked)
    pending = verify_code(MemoryStore(DEMO_VERSIONS), PENDING.verification_code, _verifier(reader))
    assert isinstance(pending, VerifyPending)
    assert reader.reads == 0


def test_not_found_does_not_touch_the_chain() -> None:
    reader = FakeReader()
    result = verify_code(MemoryStore(DEMO_VERSIONS), "ZZZZ-ZZZZ-ZZZZ-ZZZZ", _verifier(reader))
    assert result.model_dump() == {"outcome": "not_found"}
    assert reader.reads == 0


# --- cache and outage behavior ---------------------------------------------------------


def test_a_filled_slot_is_read_once_then_served_from_cache() -> None:
    reader, clock = FakeReader(), Clock()
    verifier = _verifier(reader, clock)
    for _ in range(5):
        assert verifier.check(CODE_HASH, GOOD, tx_hash="0x1").status == "verified"
    assert (reader.reads, reader.block_lookups) == (1, 1)
    clock.now += FILLED_TTL_SECONDS - 1
    verifier.check(CODE_HASH, GOOD, tx_hash="0x1")
    assert reader.reads == 1
    clock.now += 2
    verifier.check(CODE_HASH, GOOD, tx_hash="0x1")
    assert reader.reads == 2


def test_cache_holds_the_chain_value_so_a_corrected_database_is_seen_at_once() -> None:
    reader = FakeReader()
    verifier = _verifier(reader)
    assert verifier.check(CODE_HASH, OTHER).status == "mismatch"
    assert verifier.check(CODE_HASH, GOOD).status == "verified"
    assert reader.reads == 1


def test_empty_slot_is_cached_only_briefly() -> None:
    reader, clock = FakeReader({}), Clock()
    verifier = _verifier(reader, clock)
    assert verifier.check(CODE_HASH, GOOD).status == "missing"
    assert verifier.check(CODE_HASH, GOOD).status == "missing"
    assert reader.reads == 1
    reader.slots[CODE_HASH] = GOOD  # mined meanwhile
    clock.now += 61
    assert verifier.check(CODE_HASH, GOOD).status == "verified"
    assert reader.reads == 2


def test_after_a_failure_the_rpc_is_left_alone_for_a_while() -> None:
    reader, clock = FakeReader(), Clock()
    reader.down = True
    verifier = _verifier(reader, clock)
    assert verifier.check(CODE_HASH, GOOD).status == "unavailable"
    assert verifier.check(CODE_HASH, GOOD).status == "unavailable"
    assert reader.reads == 1  # the second answer did not wait for another timeout
    reader.down = False
    clock.now += OUTAGE_BACKOFF_SECONDS + 1
    assert verifier.check(CODE_HASH, GOOD).status == "verified"


def test_a_cached_filled_slot_still_answers_while_the_rpc_is_down() -> None:
    reader = FakeReader()
    verifier = _verifier(reader)
    assert verifier.check(CODE_HASH, GOOD).status == "verified"
    reader.down = True
    other_hash = bytes.fromhex("cd" * 32)
    assert verifier.check(other_hash, GOOD).status == "unavailable"
    assert verifier.check(CODE_HASH, GOOD).status == "verified"


def test_block_lookup_is_cached_and_failure_is_not_cached_as_a_block() -> None:
    reader = FakeReader()
    verifier = _verifier(reader)
    first = verifier.check(CODE_HASH, GOOD, tx_hash="0xaa")
    assert first.block_number == 4242
    assert verifier.check(CODE_HASH, GOOD, tx_hash="0xaa").block_number == 4242
    assert reader.block_lookups == 1


def test_cache_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(onchain, "CACHE_ENTRIES", 3)
    reader = FakeReader({})
    verifier = _verifier(reader)
    for index in range(10):
        verifier.check(bytes([index]) * 32, GOOD)
    assert len(verifier._slots) == 3  # noqa: SLF001


# --- web3 reader (mocked connection) ---------------------------------------------------


def _web3_reader() -> tuple[Web3AnchorReader, MagicMock, MagicMock]:
    reader = Web3AnchorReader("http://localhost:1", "0x" + "ab" * 20, 3.0)
    w3 = MagicMock()
    reader._w3 = w3  # noqa: SLF001
    contract = MagicMock()
    reader._contract = contract  # noqa: SLF001
    return reader, w3, contract


def test_web3_reader_calls_anchors_with_the_verification_id_hash() -> None:
    reader, _, contract = _web3_reader()
    contract.functions.anchors.return_value.call.return_value = GOOD
    assert reader.read_anchor(CODE_HASH) == GOOD
    contract.functions.anchors.assert_called_once_with(CODE_HASH)


def test_web3_reader_gives_the_receipt_block_or_none_when_unknown() -> None:
    reader, w3, _ = _web3_reader()
    w3.eth.get_transaction_receipt.return_value = {"blockNumber": 77}
    assert reader.block_of("0x" + "11" * 32) == 77
    w3.eth.get_transaction_receipt.side_effect = TransactionNotFound("x")
    assert reader.block_of("0x" + "11" * 32) is None


def test_web3_reader_uses_a_short_timeout_and_no_retries() -> None:
    reader = Web3AnchorReader("http://localhost:1", "0x" + "ab" * 20, 3.0)
    provider: Any = reader._w3.provider  # noqa: SLF001
    assert provider._request_kwargs["timeout"] == 3.0  # noqa: SLF001
    assert provider._exception_retry_configuration is None  # noqa: SLF001


# --- settings --------------------------------------------------------------------------


def test_verifier_needs_an_rpc_url_and_can_be_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    onchain.clear_verifiers()
    assert verifier_from_settings() is None
    monkeypatch.setattr(settings, "amoy_rpc_url", "http://localhost:1")
    first = verifier_from_settings()
    assert first is not None
    assert verifier_from_settings() is first  # one shared instance, so one shared cache
    monkeypatch.setattr(settings, "onchain_verify", False)
    assert verifier_from_settings() is None
    onchain.clear_verifiers()


def test_contract_address_defaults_to_the_published_one(monkeypatch: pytest.MonkeyPatch) -> None:
    assert onchain.contract_address() == onchain.PUBLISHED_CONTRACT_ADDRESS
    monkeypatch.setattr(settings, "anchor_contract_address", "0x" + "ab" * 20)
    assert onchain.contract_address().lower() == "0x" + "ab" * 20


# --- HTTP ------------------------------------------------------------------------------


def test_endpoint_returns_tampered_and_verified_bodies(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)
    reader = FakeReader()
    verifier = _verifier(reader)
    monkeypatch.setattr("passport_api.api.verify.verifier_from_settings", lambda: verifier)
    good = client.post("/verify", json={"code": CODE}).json()
    assert good["outcome"] == "valid"
    assert good["onchain"]["status"] == "verified"
    reader.slots[CODE_HASH] = OTHER
    verifier._slots.clear()  # noqa: SLF001
    bad = client.post("/verify", json={"code": CODE}).json()
    assert bad["outcome"] == "tampered"
    assert "holder_name" not in bad
    assert "skills" not in bad


# --- standalone script -----------------------------------------------------------------


def _script() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "verify_onchain.py"
    spec = importlib.util.spec_from_file_location("verify_onchain", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PASSPORT_JSON = {
    "holder_name": CURRENT.holder_name,
    "passport_id": CURRENT.passport_id,
    "version": CURRENT.version,
    "skills": [{"skill": "Machine Learning", "badge": "Stamp", "awarded_on": "2025-06-01"}],
}


def test_script_confirms_a_passport_the_contract_holds() -> None:
    status, lines = _script().check(FakeReader(), CODE, PASSPORT_JSON)
    assert status == 0
    assert "VERIFIED" in lines[-1]


def test_script_flags_a_changed_passport_a_missing_anchor_and_an_outage() -> None:
    script = _script()
    changed = {**PASSPORT_JSON, "holder_name": "Someone Else"}
    assert script.check(FakeReader(), CODE, changed)[0] == 1
    assert script.check(FakeReader({}), CODE, PASSPORT_JSON)[0] == 1
    down = FakeReader()
    down.down = True
    assert script.check(down, CODE, PASSPORT_JSON)[0] == 2


# --- published ABI ---------------------------------------------------------------------


def test_published_abi_matches_the_artifact_the_backend_uses() -> None:
    published = json.loads(
        (
            Path(__file__).resolve().parents[2] / "docs" / "contract" / "PassportAnchor.abi.json"
        ).read_text()
    )
    assert published == contract_abi()
