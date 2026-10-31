"""Anchor reconciliation over HTTP and the database store: the endpoint, the admin retry,
the pending list, what students see, and the migration."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fake_chain import FakeChain
from fastapi.testclient import TestClient

import passport_api.api.admin as admin_mod
from passport_api.api.me import passport_response
from passport_api.api.sync import get_sync_store
from passport_api.demo_data import DEMO_VERSIONS
from passport_api.main import app
from passport_api.settings import settings
from passport_api.store import normalize_anchor_status
from passport_api.sync import MemorySyncStore, SupabaseSyncStore, VersionRecord

client = TestClient(app)
REPO = Path(__file__).resolve().parents[2]
TOKEN = "expected-sync-token"  # noqa: S105
VERSION_ID = "aaaaaaaa-0001-4000-8000-000000000001"


def _record(**changes: Any) -> VersionRecord:
    base = VersionRecord(
        passport_id="BTU-AI-0001",
        email="ada@btu.edu.ge",
        version_number=1,
        holder_name="Ada Lovelace",
        verification_code="ABCD-EFGH-JKMN-PQRS",
        verification_id_hash="0x" + "22" * 32,
        skill_fingerprint="0x" + "33" * 32,
        content_hash="0x" + "11" * 32,
        anchor_status="pending",
        pdf_en_path=None,
        pdf_ka_path=None,
        tx_hash=None,
        issued_at="2026-10-31T11:00:00+00:00",
        skills=(),
    )
    return replace(base, **changes)


class _AdminStore(MemorySyncStore):
    """MemorySyncStore plus the one lookup the admin retry needs."""

    def version_by_id(self, version_id: str) -> VersionRecord | None:
        return next((v for v in self.versions if version_id == VERSION_ID), None)


def _admin(monkeypatch: pytest.MonkeyPatch, store: _AdminStore, chain: FakeChain | None) -> None:
    monkeypatch.setattr(admin_mod, "require_admin", lambda _auth: "admin@btu.edu.ge")
    monkeypatch.setattr("passport_api.sync.SupabaseSyncStore", lambda: store)
    monkeypatch.setattr(admin_mod, "chain_from_settings", lambda: chain)


def _retry() -> Any:
    return client.post(
        f"/admin/versions/{VERSION_ID}/anchor", headers={"Authorization": "Bearer x"}
    )


# --- the reconcile endpoint -----------------------------------------------------------------


def test_reconcile_endpoint_needs_the_sync_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "sync_token", TOKEN)
    chain = FakeChain()
    monkeypatch.setattr("passport_api.api.sync.chain_from_settings", lambda: chain)
    store = MemorySyncStore()
    store.versions.append(_record())
    app.dependency_overrides[get_sync_store] = lambda: store
    try:
        missing = client.post("/internal/anchors/reconcile")
        wrong = client.post("/internal/anchors/reconcile", headers={"X-Sync-Token": "nope"})
    finally:
        app.dependency_overrides.clear()
    assert missing.status_code == wrong.status_code == 401
    assert missing.json() == {"code": "sync_unauthorized"}
    assert chain.sent == []
    assert store.versions[0].anchor_status == "pending"


def test_reconcile_endpoint_unset_token_is_never_authorized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "sync_token", "")
    response = client.post("/internal/anchors/reconcile", headers={"X-Sync-Token": ""})
    assert response.status_code == 401


def test_reconcile_endpoint_confirms_and_reports_counts_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "sync_token", TOKEN)
    chain = FakeChain()
    monkeypatch.setattr("passport_api.api.sync.chain_from_settings", lambda: chain)
    store = MemorySyncStore()
    store.versions.append(_record())
    app.dependency_overrides[get_sync_store] = lambda: store
    try:
        response = client.post("/internal/anchors/reconcile", headers={"X-Sync-Token": TOKEN})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == {
        "status": "completed",
        "checked": 1,
        "confirmed": 1,
        "submitted": 1,
        "replaced": 0,
        "retrying": 0,
        "failed_permanent": 0,
        "waiting": 0,
        "error": None,
    }
    assert store.versions[0].anchor_status == "confirmed"


def test_reconcile_endpoint_without_a_chain_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "sync_token", TOKEN)
    monkeypatch.setattr("passport_api.api.sync.chain_from_settings", lambda: None)
    app.dependency_overrides[get_sync_store] = MemorySyncStore
    try:
        response = client.post("/internal/anchors/reconcile", headers={"X-Sync-Token": TOKEN})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["status"] == "no_chain"


# --- admin retry ----------------------------------------------------------------------------


def test_admin_retry_revives_a_failed_permanent_version(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _AdminStore()
    store.versions.append(
        _record(
            anchor_status="failed_permanent",
            anchor_attempts=6,
            anchor_last_error="rpc_error: boom",
        )
    )
    chain = FakeChain()
    _admin(monkeypatch, store, chain)
    response = _retry()
    assert response.status_code == 200
    assert response.json() == {"status": "confirmed"}
    version = store.versions[0]
    assert version.anchor_status == "confirmed"
    assert version.anchor_attempts == 1  # reset to 0, then the one new send
    assert len(chain.sent) == 1


def test_admin_retry_ignores_the_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _AdminStore()
    later = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    store.versions.append(
        _record(anchor_status="retrying", anchor_attempts=2, anchor_next_attempt_at=later)
    )
    chain = FakeChain()
    _admin(monkeypatch, store, chain)
    assert _retry().json() == {"status": "confirmed"}


def test_admin_retry_never_sends_a_hash_that_is_already_on_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _AdminStore()
    store.versions.append(_record(anchor_status="failed_permanent", anchor_attempts=6))
    chain = FakeChain()
    chain.slots[bytes.fromhex("22" * 32)] = bytes.fromhex("11" * 32)
    chain.find_anchor_tx = lambda *_: "0x" + "ee" * 32  # type: ignore[method-assign]
    _admin(monkeypatch, store, chain)
    assert _retry().json() == {"status": "confirmed"}
    assert chain.sent == []
    assert store.versions[0].tx_hash == "0x" + "ee" * 32


def test_admin_retry_reports_the_problem_when_it_still_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _AdminStore()
    store.versions.append(_record(anchor_status="failed_permanent", anchor_attempts=6))
    chain = FakeChain()
    chain.slots[bytes.fromhex("22" * 32)] = bytes.fromhex("99" * 32)
    _admin(monkeypatch, store, chain)
    response = _retry()
    assert response.status_code == 200
    assert response.json() == {"status": "failed_permanent", "error": "slot_conflict"}


def test_admin_retry_while_a_run_is_in_progress_is_a_409(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _AdminStore()
    store.versions.append(_record(anchor_status="failed_permanent", anchor_attempts=6))
    now = datetime.now(UTC)
    assert store.try_lock_anchors(now, now + timedelta(minutes=5))
    chain = FakeChain()
    _admin(monkeypatch, store, chain)
    response = _retry()
    assert response.status_code == 409
    assert response.json() == {"code": "anchor_busy"}
    assert chain.sent == []
    assert store.versions[0].anchor_status == "failed_permanent"


def test_admin_retry_on_a_confirmed_version_is_a_409(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _AdminStore()
    store.versions.append(_record(anchor_status="confirmed", tx_hash="0x" + "ab" * 32))
    chain = FakeChain()
    _admin(monkeypatch, store, chain)
    response = _retry()
    assert response.status_code == 409
    assert response.json() == {"code": "anchor_already_confirmed"}
    assert chain.sent == []


def test_admin_retry_without_a_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _AdminStore()
    store.versions.append(_record())
    _admin(monkeypatch, store, None)
    assert _retry().json() == {"status": "no_chain_configured"}


# --- pending list ---------------------------------------------------------------------------


def test_pending_list_shows_status_attempts_and_the_last_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(admin_mod, "require_admin", lambda _auth: "admin@btu.edu.ge")
    rows = [
        {
            "id": VERSION_ID,
            "version_number": 2,
            "holder_name": "Ada",
            "anchor_status": "failed_permanent",
            "tx_hash": "0x" + "ab" * 32,
            "issued_at": "2026-10-31T10:00:00+00:00",
            "anchor_attempts": 6,
            "anchor_last_error": "stuck_max_attempts",
            "anchor_submitted_at": "2026-10-31T11:00:00+00:00",
            "anchor_next_attempt_at": None,
            "students": {"passport_id": "BTU-AI-0001"},
        },
        {
            "id": "aaaaaaaa-0002-4000-8000-000000000002",
            "version_number": 1,
            "holder_name": "Grace",
            "anchor_status": "failed",  # legacy value
            "tx_hash": None,
            "issued_at": "2026-10-30T10:00:00+00:00",
            "students": {"passport_id": "BTU-AI-0002"},
        },
    ]
    with patch("passport_api.api.admin.get_supabase") as db:
        query = db.return_value.table.return_value.select.return_value
        query.neq.return_value.order.return_value.execute.return_value.data = rows
        response = client.get("/admin/versions/pending", headers={"Authorization": "Bearer x"})
        query.neq.assert_called_once_with("anchor_status", "confirmed")
    assert response.status_code == 200
    first, second = response.json()["versions"]
    assert first["anchor_status"] == "failed_permanent"
    assert first["anchor_attempts"] == 6
    assert first["anchor_last_error"] == "stuck_max_attempts"
    assert second["anchor_status"] == "retrying"
    assert second["anchor_attempts"] == 0
    assert second["anchor_last_error"] is None


# --- what students see ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stored", "shown"),
    [
        ("pending", "pending"),
        ("retrying", "pending"),
        ("confirmed", "confirmed"),
        ("failed_permanent", "failed"),
    ],
)
def test_students_see_three_anchor_states(stored: str, shown: str) -> None:
    version = replace(DEMO_VERSIONS[1], anchor_status=normalize_anchor_status(stored))
    body = passport_response((version,)).model_dump()
    assert body["passport"]["versions"][0]["anchor"]["status"] == shown


# --- the database store ---------------------------------------------------------------------


def test_supabase_store_saves_every_anchor_field() -> None:
    record = _record(
        anchor_status="retrying",
        tx_hash="0x" + "aa" * 32,
        anchor_nonce=7,
        anchor_gas_price=30_000_000_000,
        anchor_submitted_at="2026-10-31T12:00:00+00:00",
        anchor_attempts=2,
        anchor_last_error="reverted",
        anchor_next_attempt_at="2026-10-31T12:04:00+00:00",
        anchor_tx_hashes=["0x" + "bb" * 32, "0x" + "aa" * 32],
    )
    with patch("passport_api.sync.get_supabase") as db:
        table = db.return_value.table
        lookup = table.return_value.select.return_value.eq.return_value.limit.return_value
        lookup.execute.return_value.data = [{"id": "student-1"}]
        SupabaseSyncStore().save_anchor(record.email, 1, record)
        written = table.return_value.update.call_args.args[0]
    assert written == {
        "anchor_status": "retrying",
        "tx_hash": "0x" + "aa" * 32,
        "anchored_at": None,
        "anchor_nonce": 7,
        "anchor_gas_price": 30_000_000_000,
        "anchor_submitted_at": "2026-10-31T12:00:00+00:00",
        "anchor_attempts": 2,
        "anchor_last_error": "reverted",
        "anchor_next_attempt_at": "2026-10-31T12:04:00+00:00",
        "anchor_tx_hashes": ["0x" + "bb" * 32, "0x" + "aa" * 32],
    }


def test_supabase_store_reads_pending_work_and_skips_finished_versions() -> None:
    row = {
        "id": VERSION_ID,
        "version_number": 3,
        "holder_name": "Ada",
        "verification_code": "ABCD-EFGH-JKMN-PQRS",
        "verification_id_hash": "0x" + "22" * 32,
        "skill_fingerprint": "0x" + "33" * 32,
        "content_hash": "0x" + "11" * 32,
        "anchor_status": "retrying",
        "tx_hash": "0x" + "aa" * 32,
        "anchored_at": None,
        "issued_at": "2026-10-31T11:00:00+00:00",
        "anchor_nonce": 4,
        "anchor_gas_price": 31_000_000_000,
        "anchor_submitted_at": "2026-10-31T12:00:00+00:00",
        "anchor_attempts": 2,
        "anchor_last_error": "reverted",
        "anchor_next_attempt_at": None,
        "anchor_tx_hashes": ["0x" + "aa" * 32],
        "skill_entries": [],
        "students": {"email": "ada@btu.edu.ge", "passport_id": "BTU-AI-0001"},
    }
    with patch("passport_api.sync.get_supabase") as db:
        select = db.return_value.table.return_value.select
        select.return_value.in_.return_value.order.return_value.execute.return_value.data = [row]
        records = SupabaseSyncStore().pending_anchors()
        statuses = select.return_value.in_.call_args.args[1]
    assert set(statuses) == {"pending", "retrying", "failed"}
    assert "confirmed" not in statuses and "failed_permanent" not in statuses
    assert len(records) == 1
    record = records[0]
    assert (record.anchor_nonce, record.anchor_gas_price, record.anchor_attempts) == (
        4,
        31_000_000_000,
        2,
    )
    assert record.anchor_tx_hashes == ["0x" + "aa" * 32]
    assert record.anchor_last_error == "reverted"


def test_supabase_lock_is_one_conditional_update() -> None:
    now = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
    until = now + timedelta(minutes=5)
    with patch("passport_api.sync.get_supabase") as db:
        table = db.return_value.table
        update = table.return_value.update
        guarded = update.return_value.eq.return_value.lt.return_value.execute
        guarded.return_value.data = [{"name": "reconciler"}]
        assert SupabaseSyncStore().try_lock_anchors(now, until) is True
        table.assert_called_with("anchor_reconcile_lock")
        assert update.call_args.args[0] == {"locked_until": until.isoformat()}
        update.return_value.eq.assert_called_with("name", "reconciler")
        update.return_value.eq.return_value.lt.assert_called_with("locked_until", now.isoformat())
        guarded.return_value.data = []
        assert SupabaseSyncStore().try_lock_anchors(now, until) is False


def test_supabase_unlock_clears_the_lock() -> None:
    with patch("passport_api.sync.get_supabase") as db:
        update = db.return_value.table.return_value.update
        SupabaseSyncStore().unlock_anchors()
        assert update.call_args.args[0] == {"locked_until": "1970-01-01T00:00:00+00:00"}


# --- migration and workflow -----------------------------------------------------------------


def test_migration_is_idempotent_and_covers_every_column_the_code_writes() -> None:
    sql = (REPO / "supabase" / "migrations" / "0010_anchor_reliability.sql").read_text()
    for column in (
        "anchor_nonce",
        "anchor_gas_price",
        "anchor_submitted_at",
        "anchor_attempts",
        "anchor_last_error",
        "anchor_next_attempt_at",
        "anchor_tx_hashes",
    ):
        assert f"add column if not exists {column}" in sql
    assert "drop constraint if exists passport_versions_anchor_status" in sql
    assert "'retrying'" in sql and "'failed_permanent'" in sql and "'failed'" in sql
    assert "create table if not exists anchor_reconcile_lock" in sql
    assert "on conflict (name) do nothing" in sql
    assert "create index if not exists" in sql
    assert "alter table anchor_reconcile_lock enable row level security" in sql
    lowered = sql.lower()
    assert "drop table" not in lowered and "drop column" not in lowered


def test_workflow_calls_the_reconcile_endpoint_even_when_the_sync_fails() -> None:
    workflow = (REPO / ".github" / "workflows" / "sync.yml").read_text()
    assert '"${{ secrets.SYNC_URL }}/internal/anchors/reconcile"' in workflow
    assert workflow.count("X-Sync-Token: ${{ secrets.SYNC_TOKEN }}") == 2
    assert "!cancelled()" in workflow
    assert "needs: sync" in workflow
