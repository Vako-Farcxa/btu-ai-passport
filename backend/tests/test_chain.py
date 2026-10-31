import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from eth_account import Account
from fake_chain import FakeChain
from web3 import Web3

from passport_api.anchoring import reconcile_anchors
from passport_api.chain import encode_anchor_call, tx_url
from passport_api.settings import Settings, settings
from passport_api.store import MemoryStore, StoredVersion, normalize_anchor_status
from passport_api.sync import FakeSheet, MemorySyncStore, VersionRecord, run_sync
from passport_api.verify import VerifyFound, VerifyPending, verify_code

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


def _publish_version(chain: FakeChain) -> VersionRecord:
    """One unconfirmed version run through the reconciler, like a sync does."""
    store = MemorySyncStore()
    store.versions.append(_record())
    reconcile_anchors(store, chain)
    return store.versions[0]


def _record() -> VersionRecord:
    return VersionRecord(
        passport_id="BTU-AI-0001",
        email=EMAIL,
        version_number=1,
        holder_name=HOLDER,
        verification_code="ABCD-EFGH-JKMN-PQRS",
        verification_id_hash=VERIFICATION,
        skill_fingerprint="0x" + "55" * 32,
        content_hash=CONTENT,
        anchor_status="pending",
        pdf_en_path=None,
        pdf_ka_path=None,
        tx_hash=None,
        issued_at=NOW,
        skills=(),
    )


def test_anchor_payload_is_two_bytes32_and_omits_personal_data() -> None:
    chain = FakeChain()
    version = _publish_version(chain)
    assert version.anchor_status == "confirmed"
    assert len(chain.sent) == 1
    payload = encode_anchor_call(CONTENT, VERIFICATION)
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
    for secret in (HOLDER, EMAIL, SKILL, BADGE):
        assert secret.encode() not in payload


def test_successful_receipt_confirms_and_builds_the_amoy_url() -> None:
    chain = FakeChain()
    version = _publish_version(chain)
    assert version.anchor_status == "confirmed"
    assert version.tx_hash == "0x" + f"{1:064x}"
    assert version.anchored_at is not None
    assert tx_url(version.tx_hash) == f"https://amoy.polygonscan.com/tx/{version.tx_hash}"


def test_wrong_chain_or_sender_does_not_send() -> None:
    wrong_chain = FakeChain()
    wrong_chain.chain_id_value = 1
    version = _publish_version(wrong_chain)
    assert wrong_chain.sent == []
    assert version.anchor_status == "pending"
    assert version.anchor_attempts == 0

    wrong_sender = FakeChain()
    wrong_sender.sender = "0x9999999999999999999999999999999999999999"
    other = _publish_version(wrong_sender)
    assert wrong_sender.sent == []
    assert other.anchor_status == "pending"
    assert other.tx_hash is None


def test_confirmed_anchor_is_left_unchanged() -> None:
    chain = FakeChain()
    store = MemorySyncStore()
    version = _record()
    version.anchor_status = "confirmed"
    version.tx_hash = "0x" + "ab" * 32
    version.anchored_at = "2026-01-01T00:00:00+00:00"
    store.versions.append(version)
    reconcile_anchors(store, chain)
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
    chain = FakeChain()
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
    assert b"ada@btu.edu.ge" not in chain.payloads[0]
    assert b"Ada Lovelace" not in chain.payloads[0]
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
    chain = FakeChain()
    chain.send_error = ConnectionError("rpc down")
    store = MemorySyncStore()
    rows = [_row("ada@btu.edu.ge", "Ada Lovelace", "Python", "Core", "2025-01-15")]
    failed = run_sync(store, FakeSheet(rows), chain=chain)
    assert failed.status == "completed"
    assert failed.versions_created == 1
    assert store.versions[0].anchor_status == "retrying"
    assert store.versions[0].tx_hash is None
    # The public sees "pending", never an error, while the reconciler keeps trying.
    waiting = verify_code(_memory(store.versions), store.versions[0].verification_code)
    assert isinstance(waiting, VerifyPending)
    assert waiting.outcome == "pending"
    chain.send_error = None
    # The backoff has passed.
    store.versions[0].anchor_next_attempt_at = None
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
                anchor_status=normalize_anchor_status(version.anchor_status),
                tx_hash=version.tx_hash,
                issued_at=version.issued_at,
                skills=version.skills,
            )
            for version in versions
        ]
    )


def _deploy_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("deploy_anchor", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
