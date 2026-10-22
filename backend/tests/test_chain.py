import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Literal

import pytest
from eth_account import Account
from web3 import Web3

from passport_api.chain import publish_anchor, tx_url
from passport_api.settings import Settings, settings
from passport_api.store import MemoryStore, StoredVersion
from passport_api.sync import FakeSheet, MemorySyncStore, VersionRecord, run_sync
from passport_api.verify import VerifyError, VerifyFound, verify_code

REPO = Path(__file__).resolve().parents[2]
ASSETS = REPO / "backend" / "assets" / "PassportAnchor.json"
CONTRACT = REPO / "specs" / "001-ai-skills-passport" / "contracts" / "PassportAnchor.sol"
SCRIPT = REPO / "backend" / "scripts" / "deploy_anchor.py"

CONTENT = "0x" + "11" * 32
VERIFICATION = "0x" + "22" * 32
HOLDER = "ნინო ბერიძე"
EMAIL = "nino.beridze@btu.edu.ge"
SKILL = "Machine Learning"
BADGE = "Stamp-Secret"
NOW = "2026-10-23T00:00:00+00:00"
ISSUER = "0x1111111111111111111111111111111111111111"


@dataclass
class AnchorVersion:
    content_hash: str
    verification_id_hash: str
    holder_name: str
    email: str
    skill: str
    badge: str
    anchor_status: str = "pending"
    tx_hash: str | None = None
    anchored_at: str | None = None


class RecordingChain:
    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.slots: dict[bytes, bytes] = {}
        self.receipts: dict[str, bool | None] = {}
        self.fail_send = False
        self.leave_pending = False
        self.fail_receipt = False
        self.chain_id_value = 80002
        self.issuer = ISSUER
        self.sender = ISSUER
        self._next = 1

    def chain_id(self) -> int:
        return self.chain_id_value

    def issuer_address(self) -> str:
        return self.issuer

    def sender_address(self) -> str:
        return self.sender

    def stored_content(self, verification_id_hash: bytes) -> bytes:
        return self.slots.get(verification_id_hash, bytes(32))

    def send_anchor(self, data: bytes) -> str:
        if self.fail_send:
            raise ConnectionError("send_failed")
        self.sent.append(data)
        tx_hash = "0x" + f"{self._next:064x}"
        self._next += 1
        if self.leave_pending:
            self.receipts[tx_hash] = None
        elif self.fail_receipt:
            self.receipts[tx_hash] = False
        return tx_hash

    def receipt_succeeded(self, tx_hash: str) -> bool | None:
        if tx_hash in self.receipts:
            return self.receipts[tx_hash]
        return True


def _version() -> AnchorVersion:
    return AnchorVersion(
        content_hash=CONTENT,
        verification_id_hash=VERIFICATION,
        holder_name=HOLDER,
        email=EMAIL,
        skill=SKILL,
        badge=BADGE,
    )


def _publish(version: AnchorVersion, chain: RecordingChain) -> None:
    publish_anchor(version, chain, now=NOW)


def test_anchor_payload_is_two_bytes32_and_omits_personal_data() -> None:
    chain = RecordingChain()
    version = _version()
    _publish(version, chain)
    assert version.anchor_status == "confirmed"
    assert len(chain.sent) == 1
    payload = chain.sent[0]
    selector = Web3.keccak(text="anchor(bytes32,bytes32)")[:4]
    assert payload[:4] == selector
    assert payload[4:36] == bytes.fromhex(CONTENT[2:])
    assert payload[36:68] == bytes.fromhex(VERIFICATION[2:])
    assert len(payload) == 68
    artifact = json.loads(ASSETS.read_text())
    functions = [item for item in artifact["abi"] if item.get("type") == "function"]
    anchor = next(item for item in functions if item.get("name") == "anchor")
    assert [(item["name"], item["type"]) for item in anchor["inputs"]] == [
        ("contentHash", "bytes32"),
        ("verificationIdHash", "bytes32"),
    ]
    assert all(item["type"] == "bytes32" for item in anchor["inputs"])
    for secret in (HOLDER, EMAIL, SKILL, BADGE, version.holder_name):
        assert secret.encode() not in payload


def test_filled_slot_does_not_send_a_second_anchor() -> None:
    chain = RecordingChain()
    chain.slots[bytes.fromhex(VERIFICATION[2:])] = bytes.fromhex("33" * 32)
    version = _version()
    _publish(version, chain)
    assert chain.sent == []
    assert version.anchor_status == "pending"
    assert version.tx_hash is None
    assert version.anchored_at is None


def test_successful_receipt_confirms_and_builds_the_amoy_url() -> None:
    chain = RecordingChain()
    version = _version()
    _publish(version, chain)
    assert version.anchor_status == "confirmed"
    assert version.tx_hash == "0x" + f"{1:064x}"
    assert version.anchored_at == NOW
    assert version.tx_hash is not None
    assert tx_url(version.tx_hash) == f"https://amoy.polygonscan.com/tx/{version.tx_hash}"


def test_failed_send_marks_failed_and_a_later_success_confirms() -> None:
    chain = RecordingChain()
    version = _version()
    chain.fail_send = True
    _publish(version, chain)
    assert version.anchor_status == "failed"
    assert version.tx_hash is None
    assert version.anchored_at is None
    assert chain.sent == []
    chain.fail_send = False
    _publish(version, chain)
    assert version.anchor_status == "confirmed"
    assert version.tx_hash == "0x" + f"{1:064x}"
    assert version.anchored_at == NOW
    assert len(chain.sent) == 1


def test_pending_receipt_is_polled_without_a_second_send() -> None:
    chain = RecordingChain()
    version = _version()
    chain.leave_pending = True
    _publish(version, chain)
    assert version.anchor_status == "pending"
    assert version.tx_hash == "0x" + f"{1:064x}"
    assert version.anchored_at is None
    assert version.tx_hash is not None
    chain.leave_pending = False
    chain.receipts[version.tx_hash] = True
    _publish(version, chain)
    assert len(chain.sent) == 1
    assert version.anchor_status == "confirmed"
    assert version.anchored_at == NOW


def test_reverted_receipt_stays_failed_until_a_slot_is_empty_retry_succeeds() -> None:
    chain = RecordingChain()
    version = _version()
    chain.fail_receipt = True
    _publish(version, chain)
    assert version.anchor_status == "failed"
    assert version.tx_hash == "0x" + f"{1:064x}"
    assert version.anchored_at is None
    chain.fail_receipt = False
    chain.slots[bytes.fromhex(VERIFICATION[2:])] = bytes.fromhex("44" * 32)
    _publish(version, chain)
    assert len(chain.sent) == 1
    assert version.anchor_status == "failed"
    chain.slots.clear()
    _publish(version, chain)
    assert len(chain.sent) == 2
    assert version.anchor_status == "confirmed"
    assert version.anchored_at == NOW


def test_wrong_chain_or_sender_does_not_send() -> None:
    wrong_chain = RecordingChain()
    wrong_chain.chain_id_value = 1
    version = _version()
    _publish(version, wrong_chain)
    assert wrong_chain.sent == []
    assert version.anchor_status == "failed"

    wrong_sender = RecordingChain()
    wrong_sender.sender = "0x9999999999999999999999999999999999999999"
    other = _version()
    _publish(other, wrong_sender)
    assert wrong_sender.sent == []
    assert other.anchor_status == "failed"
    assert other.tx_hash is None


def test_confirmed_anchor_is_left_unchanged() -> None:
    chain = RecordingChain()
    version = _version()
    version.anchor_status = "confirmed"
    version.tx_hash = "0x" + "ab" * 32
    version.anchored_at = "2026-01-01T00:00:00+00:00"
    _publish(version, chain)
    assert chain.sent == []
    assert version.anchor_status == "confirmed"
    assert version.tx_hash == "0x" + "ab" * 32
    assert version.anchored_at == "2026-01-01T00:00:00+00:00"


def test_chain_settings_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMOY_RPC_URL", "https://rpc.amoy.example")
    monkeypatch.setenv("ANCHOR_CONTRACT_ADDRESS", "0x" + "ab" * 20)
    monkeypatch.setenv("BTU_ISSUER_PRIVATE_KEY", "0x" + "cd" * 32)
    loaded = Settings()
    assert loaded.amoy_rpc_url == "https://rpc.amoy.example"
    assert loaded.anchor_contract_address == "0x" + "ab" * 20
    assert loaded.btu_issuer_private_key == "0x" + "cd" * 32


def test_sync_confirms_one_anchor_and_verify_flips_to_valid_then_outdated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _local_pdfs(tmp_path, monkeypatch)
    chain = RecordingChain()
    store = MemorySyncStore()
    created = run_sync(
        store,
        FakeSheet([_row("ada@btu.edu.ge", "Ada Lovelace", "Python", "Core", "2025-01-15")]),
        chain=chain,
    )
    assert created.versions_created == 1
    first = store.versions[0]
    assert first.anchor_status == "confirmed"
    assert first.tx_hash is not None
    assert first.anchored_at is not None
    assert len(chain.sent) == 1
    assert b"ada@btu.edu.ge" not in chain.sent[0]
    assert b"Ada Lovelace" not in chain.sent[0]
    looked_up = verify_code(_memory(store.versions), first.verification_code)
    assert isinstance(looked_up, VerifyFound)
    assert looked_up.outcome == "valid"
    assert looked_up.is_latest is True
    assert looked_up.tx_url == f"https://amoy.polygonscan.com/tx/{first.tx_hash}"

    again = run_sync(
        store,
        FakeSheet([_row("ada@btu.edu.ge", "Ada Lovelace", "Python", "Core", "2025-01-15")]),
        chain=chain,
    )
    assert again.versions_created == 0
    assert len(store.versions) == 1
    assert len(chain.sent) == 1

    newer = run_sync(
        store,
        FakeSheet([_row("ada@btu.edu.ge", "Ada Lovelace", "SQL", "Core", "2025-02-02")]),
        chain=chain,
    )
    assert newer.versions_created == 1
    assert len(store.versions) == 2
    assert len(chain.sent) == 2
    second = store.versions[1]
    assert second.anchor_status == "confirmed"
    current = verify_code(_memory(store.versions), second.verification_code)
    previous = verify_code(_memory(store.versions), first.verification_code)
    assert isinstance(current, VerifyFound)
    assert isinstance(previous, VerifyFound)
    assert current.outcome == "valid"
    assert previous.outcome == "outdated"
    assert previous.is_latest is False
    assert previous.tx_url == f"https://amoy.polygonscan.com/tx/{first.tx_hash}"
    assert current.tx_url == f"https://amoy.polygonscan.com/tx/{second.tx_hash}"
    assert {skill.skill for skill in previous.skills} == {"Python"}
    assert {skill.skill for skill in current.skills} == {"SQL"}


def test_sync_retries_a_failed_send_without_a_second_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _local_pdfs(tmp_path, monkeypatch)
    chain = RecordingChain()
    chain.fail_send = True
    store = MemorySyncStore()
    rows = [_row("ada@btu.edu.ge", "Ada Lovelace", "Python", "Core", "2025-01-15")]
    failed = run_sync(store, FakeSheet(rows), chain=chain)
    assert failed.status == "completed"
    assert failed.versions_created == 1
    assert store.versions[0].anchor_status == "failed"
    assert store.versions[0].tx_hash is None
    refused = verify_code(_memory(store.versions), store.versions[0].verification_code)
    assert isinstance(refused, VerifyError)
    assert refused.outcome == "error"
    chain.fail_send = False
    retried = run_sync(store, FakeSheet(rows), chain=chain)
    assert retried.versions_created == 0
    assert len(store.versions) == 1
    assert store.versions[0].anchor_status == "confirmed"
    assert len(chain.sent) == 1
    accepted = verify_code(_memory(store.versions), store.versions[0].verification_code)
    assert isinstance(accepted, VerifyFound)
    assert accepted.outcome == "valid"


def test_deploy_writes_the_artifact_from_the_issuer_wallet(tmp_path: Path) -> None:
    module = _deploy_module()
    key = "0x" + "11" * 32
    issuer = Account.from_key(key).address
    seen: dict[str, object] = {}

    def compile_source(source: str) -> tuple[list[dict[str, object]], str]:
        seen["source"] = source
        return ([{"type": "function", "name": "anchor"}], "0x6001")

    class Recorder:
        def deploy(self, bytecode: str, abi: list[dict[str, object]], sender: str) -> str:
            seen["bytecode"] = bytecode
            seen["abi"] = abi
            seen["sender"] = sender
            return "0x" + "22" * 20

    destination = tmp_path / "PassportAnchor.json"
    address = module.deploy_and_write(
        source=module.contract_source(),
        compile_source=compile_source,
        chain=Recorder(),
        private_key=key,
        destination=destination,
    )
    assert address == "0x" + "22" * 20
    assert seen["sender"] == issuer
    assert seen["bytecode"] == "0x6001"
    source = seen["source"]
    assert isinstance(source, str)
    assert "function anchor(bytes32 contentHash, bytes32 verificationIdHash)" in source
    assert "issuer = msg.sender" in source
    written = json.loads(destination.read_text())
    assert written["abi"] == [{"type": "function", "name": "anchor"}]
    assert written["bytecode"] == "0x6001"


def _local_pdfs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "pdf_storage_dir", str(tmp_path))
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_service_role_key", "")


def _row(email: str, full_name: str, skill: str, badge: str, awarded_on: str) -> dict[str, str]:
    return {
        "email": email,
        "full_name": full_name,
        "skill": skill,
        "badge": badge,
        "awarded_on": awarded_on,
    }


def _memory(versions: list[VersionRecord]) -> MemoryStore:
    return MemoryStore(
        [
            StoredVersion(
                passport_id=version.passport_id,
                email=version.email,
                full_name=version.holder_name,
                version=version.version_number,
                holder_name=version.holder_name,
                verification_code=version.verification_code,
                anchor_status=_anchor_status(version.anchor_status),
                tx_hash=version.tx_hash,
                issued_at=version.issued_at,
                skills=version.skills,
            )
            for version in versions
        ]
    )


def _anchor_status(value: str) -> Literal["pending", "confirmed", "failed"]:
    if value == "pending":
        return "pending"
    if value == "confirmed":
        return "confirmed"
    if value == "failed":
        return "failed"
    raise AssertionError(value)


def _deploy_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("deploy_anchor", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
