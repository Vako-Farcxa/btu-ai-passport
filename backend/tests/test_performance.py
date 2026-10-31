"""The speed work: connection reuse, caches, batched sync commits, diffed Sheet writes, one-call
dashboard numbers. Each test pins a behavior the speed-up must not change, or the speed-up itself
(a number of calls, never a stopwatch, so they cannot flake)."""

import threading
import time
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

import passport_api.admin_health as admin_health
import passport_api.admin_stats as admin_stats
import passport_api.api.admin as admin_mod
import passport_api.auth as auth
import passport_api.cache as cache_mod
import passport_api.db as db_mod
import passport_api.sync as sync_mod
from passport_api.cache import TtlCache, clear_all_caches
from passport_api.errors import APIError as PassportAPIError
from passport_api.main import app
from passport_api.schemas import Skill
from passport_api.settings import settings
from passport_api.sync import (
    FakeSheet,
    GspreadSheet,
    MemorySyncStore,
    RowOutcome,
    StudentUnit,
    SupabaseSyncStore,
    UnitResult,
    VersionRecord,
    run_sync,
    write_back_ranges,
)

client = TestClient(app)
AUTH = {"Authorization": "Bearer x"}


# --- the TTL cache --------------------------------------------------------------------------


def test_the_cache_keeps_a_value_until_it_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [100.0]
    monkeypatch.setattr(cache_mod, "time", SimpleNamespace(monotonic=lambda: now[0]))
    cache: TtlCache[str] = TtlCache(ttl=10)
    cache.put("a", "one")
    now[0] = 109.9
    assert cache.get("a") == "one"
    now[0] = 110.0
    assert cache.get("a") is None


def test_get_or_load_loads_once_and_never_caches_a_failure() -> None:
    cache: TtlCache[int] = TtlCache(ttl=60)
    calls: list[int] = []

    def load() -> int:
        calls.append(1)
        return 7

    assert cache.get_or_load("k", load) == 7
    assert cache.get_or_load("k", load) == 7
    assert len(calls) == 1

    def boom() -> int:
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        cache.get_or_load("other", boom)
    assert cache.get("other") is None


def test_clear_all_caches_empties_every_cache() -> None:
    first: TtlCache[int] = TtlCache(ttl=60)
    second: TtlCache[int] = TtlCache(ttl=60)
    first.put("a", 1)
    second.put("b", 2)
    clear_all_caches()
    assert first.get("a") is None
    assert second.get("b") is None


# --- one supabase client for the whole process ----------------------------------------------


def test_the_supabase_client_is_built_once_and_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "supabase_url", "https://a.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "key-a")
    made: list[tuple[str, str]] = []

    def create(url: str, key: str) -> object:
        made.append((url, key))
        return object()

    monkeypatch.setattr(db_mod, "create_client", create)
    first = db_mod.get_supabase()
    assert db_mod.get_supabase() is first
    assert made == [("https://a.supabase.co", "key-a")]


def test_a_changed_setting_or_a_reset_builds_a_new_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "supabase_url", "https://a.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "key-a")
    monkeypatch.setattr(db_mod, "create_client", lambda url, key: object())
    first = db_mod.get_supabase()
    monkeypatch.setattr(settings, "supabase_service_role_key", "key-b")
    second = db_mod.get_supabase()
    assert second is not first
    db_mod.reset_client()
    assert db_mod.get_supabase() is not second


def test_threads_share_one_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "supabase_url", "https://a.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "key-a")
    made: list[object] = []

    def create(url: str, key: str) -> object:
        time.sleep(0.01)
        made.append(object())
        return made[-1]

    monkeypatch.setattr(db_mod, "create_client", create)
    seen: list[object] = []
    threads = [
        threading.Thread(target=lambda: seen.append(db_mod.get_supabase())) for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(made) == 1
    assert len({id(client_) for client_ in seen}) == 1


# --- /admin/stats ---------------------------------------------------------------------------


class _Result:
    def __init__(self, data: object = None, count: int | None = None) -> None:
        self.data = data
        self.count = count


class _CountQuery:
    """Records the filters of a head-count query and answers with a count by table."""

    def __init__(self, db: "_StatsDb", table: str) -> None:
        self._db = db
        self._table = table
        self.filters: list[str] = []
        self._rows: object = None

    def select(self, columns: str, count: object = None) -> "_CountQuery":
        self.filters.append("select")
        return self

    def is_(self, column: str, value: str) -> "_CountQuery":
        self.filters.append(f"is {column}")
        return self

    def eq(self, column: str, value: object) -> "_CountQuery":
        self.filters.append(f"eq {column}")
        return self

    def neq(self, column: str, value: object) -> "_CountQuery":
        self.filters.append(f"neq {column}")
        return self

    @property
    def not_(self) -> "_CountQuery":
        self.filters.append("not")
        return self

    def in_(self, column: str, values: list[str]) -> "_CountQuery":
        self.filters.append(f"in {column}")
        return self

    def order(self, *_a: Any, **_k: Any) -> "_CountQuery":
        return self

    def limit(self, _n: int) -> "_CountQuery":
        return self

    def execute(self) -> _Result:
        self._db.reads.append((self._table, tuple(self.filters)))
        if self._table == "sync_runs":
            return _Result(self._db.runs)
        key = (self._table, tuple(f for f in self.filters if f not in {"select", "not"}))
        return _Result(None, self._db.counts.get(key, 0))


class _StatsDb:
    def __init__(self, *, function: object = None, broken: bool = False) -> None:
        self.function = function
        self.broken = broken
        self.rpcs: list[str] = []
        self.reads: list[tuple[str, tuple[str, ...]]] = []
        self.runs: list[dict[str, Any]] = []
        self.counts: dict[tuple[str, tuple[str, ...]], int] = {
            ("students", ("is deleted_at",)): 214,
            ("students", ("is deleted_at", "eq admin_managed")): 9,
            ("passport_versions", ("neq anchor_status",)): 3,
            ("passport_versions", ("in anchor_status",)): 1,
            ("flags", ("eq status",)): 2,
        }

    def rpc(self, name: str, *_args: Any) -> Any:
        self.rpcs.append(name)
        if self.broken:
            raise APIError({"code": "PGRST202", "message": "no function"})
        data = self.function
        return MagicMock(execute=lambda: _Result(data))

    def table(self, name: str) -> _CountQuery:
        return _CountQuery(self, name)


_RUN = {
    "id": "6f1f3d5e-3c8a-4f0e-9a43-5d1a3f1d0c11",
    "status": "completed",
    "started_at": "2026-10-31T12:00:00+00:00",
    "finished_at": "2026-10-31T12:00:20+00:00",
    "rows_read": 640,
    "versions_created": 0,
    "error": None,
}
_STATS = {
    "total_students": 214,
    "admin_managed_students": 9,
    "pending_anchors": 3,
    "failed_anchors": 1,
    "open_flags": 2,
    "recent_runs": [_RUN],
}


def test_the_stats_come_from_one_function_call_when_migration_0012_is_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _StatsDb(function=_STATS)
    fake.runs = [_RUN]
    monkeypatch.setattr(admin_stats, "get_supabase", lambda: fake)
    stats = admin_stats.load_admin_stats()
    assert fake.rpcs == ["admin_dashboard_stats"]
    assert fake.reads == []
    assert (stats.total_students, stats.admin_managed_students) == (214, 9)
    assert (stats.pending_anchors, stats.failed_anchors, stats.open_flags) == (3, 1, 2)
    assert [str(run.id) for run in stats.recent_runs] == [_RUN["id"]]
    assert stats.recent_runs[0].rows_read == 640


@pytest.mark.parametrize("function", [None, [], "nope"])
def test_without_the_function_the_same_numbers_are_counted_the_old_way(
    monkeypatch: pytest.MonkeyPatch, function: object
) -> None:
    fake = _StatsDb(function=function)
    fake.runs = [_RUN]
    monkeypatch.setattr(admin_stats, "get_supabase", lambda: fake)
    stats = admin_stats.load_admin_stats()
    assert fake.rpcs == ["admin_dashboard_stats"]
    assert stats.model_dump(mode="json")["total_students"] == 214
    assert (stats.admin_managed_students, stats.pending_anchors) == (9, 3)
    assert (stats.failed_anchors, stats.open_flags) == (1, 2)
    assert len(stats.recent_runs) == 1
    # Head-only counts, no rows are downloaded for them.
    tables = sorted(table for table, _ in fake.reads)
    assert tables == [
        "flags",
        "passport_versions",
        "passport_versions",
        "students",
        "students",
        "sync_runs",
    ]


def test_a_missing_function_error_also_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _StatsDb(broken=True)
    monkeypatch.setattr(admin_stats, "get_supabase", lambda: fake)
    assert admin_stats.load_admin_stats().total_students == 214


def _as_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin_mod, "require_admin", lambda _auth: "admin@btu.edu.ge")


def test_the_stats_endpoint_serves_repeat_visits_from_a_short_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _as_admin(monkeypatch)
    fake = _StatsDb(function=_STATS)
    monkeypatch.setattr(admin_stats, "get_supabase", lambda: fake)
    first = client.get("/admin/stats", headers=AUTH)
    second = client.get("/admin/stats", headers=AUTH)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["total_students"] == 214
    assert fake.rpcs == ["admin_dashboard_stats"]


def test_an_admin_write_drops_the_cached_numbers(monkeypatch: pytest.MonkeyPatch) -> None:
    _as_admin(monkeypatch)
    fake = _StatsDb(function=_STATS)
    monkeypatch.setattr(admin_stats, "get_supabase", lambda: fake)
    assert client.get("/admin/stats", headers=AUTH).status_code == 200
    # Any admin write goes through admin_write_limit, which clears the caches afterwards,
    # whatever the route answers (here: the student is already archived, a 409).
    monkeypatch.setattr(
        admin_mod,
        "_require_admin_student",
        lambda _passport_id: {"id": "s", "deleted_at": "2026-10-01T00:00:00+00:00"},
    )
    assert client.delete("/admin/students/BTU-X", headers=AUTH).status_code == 409
    assert client.get("/admin/stats", headers=AUTH).status_code == 200
    assert fake.rpcs == ["admin_dashboard_stats", "admin_dashboard_stats"]


def test_the_cache_is_not_cleared_by_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    _as_admin(monkeypatch)
    fake = _StatsDb(function=_STATS)
    monkeypatch.setattr(admin_stats, "get_supabase", lambda: fake)
    for _ in range(3):
        client.get("/admin/stats", headers=AUTH)
        client.get("/admin/me", headers=AUTH)
    assert fake.rpcs == ["admin_dashboard_stats"]


def test_a_failing_database_is_a_503_and_is_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    _as_admin(monkeypatch)
    calls: list[int] = []

    def broken() -> Any:
        calls.append(1)
        raise RuntimeError("down")

    monkeypatch.setattr(admin_stats, "get_supabase", broken)
    for _ in range(2):
        response = client.get("/admin/stats", headers=AUTH)
        assert response.status_code == 503
        assert response.json() == {"code": "stats_unavailable"}
    assert len(calls) == 2


def test_the_stats_endpoint_is_admin_only() -> None:
    assert client.get("/admin/stats").status_code == 401
    assert (
        client.get("/admin/stats", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    )


def test_the_health_endpoint_is_cached_and_the_banner_uses_one_snapshot_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _as_admin(monkeypatch)
    snapshot = {
        "last_finished_run": {
            "status": "completed",
            "started_at": "2999-01-01T00:00:00+00:00",
            "finished_at": "2999-01-01T00:00:20+00:00",
            "error": None,
        },
        "last_success_run": {
            "status": "completed",
            "started_at": "2999-01-01T00:00:00+00:00",
            "finished_at": "2999-01-01T00:00:20+00:00",
            "error": None,
        },
        "open_versions": [],
        "inconsistencies": 0,
    }
    fake = _StatsDb(function=snapshot)
    monkeypatch.setattr(admin_health, "get_supabase", lambda: fake)
    for _ in range(2):
        response = client.get("/admin/health", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    assert fake.rpcs == ["admin_health_snapshot"]
    assert fake.reads == []


# --- the admin check is remembered for a short time -----------------------------------------


def _admin_lookup(rows: list[dict[str, str]]) -> MagicMock:
    db = MagicMock()
    query = db.table.return_value.select.return_value.eq.return_value
    query.limit.return_value.execute.return_value.data = rows
    return db


def test_a_listed_admin_is_looked_up_once_not_on_every_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "email_from_authorization", lambda _h: "admin@btu.edu.ge")
    db = _admin_lookup([{"id": "1"}])
    with patch("passport_api.auth.get_supabase", return_value=db):
        assert auth.require_admin("Bearer x") == "admin@btu.edu.ge"
        assert auth.require_admin("Bearer x") == "admin@btu.edu.ge"
    assert db.table.call_count == 1


def test_a_refusal_is_never_remembered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "email_from_authorization", lambda _h: "staff@btu.edu.ge")
    db = _admin_lookup([])
    with patch("passport_api.auth.get_supabase", return_value=db):
        for _ in range(2):
            with pytest.raises(PassportAPIError) as caught:
                auth.require_admin("Bearer x")
            assert (caught.value.status_code, caught.value.code) == (403, "admin_not_found")
    assert db.table.call_count == 2


def test_removing_an_admin_takes_effect_when_the_remembered_answer_expires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [1000.0]
    monkeypatch.setattr(cache_mod, "time", SimpleNamespace(monotonic=lambda: now[0]))
    monkeypatch.setattr(auth, "email_from_authorization", lambda _h: "admin@btu.edu.ge")
    with patch("passport_api.auth.get_supabase", return_value=_admin_lookup([{"id": "1"}])):
        auth.require_admin("Bearer x")
    now[0] += 29
    with patch("passport_api.auth.get_supabase", return_value=_admin_lookup([])) as removed:
        assert auth.require_admin("Bearer x") == "admin@btu.edu.ge"  # still inside 30 s
        removed.assert_not_called()
        now[0] += 2
        with pytest.raises(PassportAPIError):
            auth.require_admin("Bearer x")


# --- archived check -------------------------------------------------------------------------


def test_the_archived_check_reads_one_column_of_one_row() -> None:
    from passport_api.supabase_store import SupabaseStore

    db = MagicMock()
    chain = db.table.return_value.select.return_value.eq.return_value.limit.return_value
    chain.execute.return_value.data = [{"deleted_at": "2026-10-01T00:00:00+00:00"}]
    with patch("passport_api.supabase_store.get_supabase", return_value=db):
        assert SupabaseStore().is_archived(" Ada@BTU.edu.ge ") is True
    db.table.assert_called_once_with("students")
    db.table.return_value.select.assert_called_once_with("deleted_at")
    db.table.return_value.select.return_value.eq.assert_called_once_with("email", "ada@btu.edu.ge")
    for rows, expected in (([], False), ([{"deleted_at": None}], False)):
        chain.execute.return_value.data = rows
        with patch("passport_api.supabase_store.get_supabase", return_value=db):
            assert SupabaseStore().is_archived("ada@btu.edu.ge") is expected


# --- sync: unchanged students are not written again -----------------------------------------

ADA = {
    "email": "ada@btu.edu.ge",
    "full_name": "Ada Lovelace",
    "skill": "Python",
    "badge": "Foundation",
    "awarded_on": "2025-01-15",
}


def _students(n: int) -> list[dict[str, str]]:
    return [{**ADA, "email": f"s{i}@btu.edu.ge", "full_name": f"Student {i}"} for i in range(n)]


class _CountingStore(MemorySyncStore):
    def __init__(self) -> None:
        super().__init__()
        self.committed: list[str] = []

    def commit_student_unit(self, unit: StudentUnit) -> UnitResult:
        self.committed.append(unit.email)
        return super().commit_student_unit(unit)


def test_an_unchanged_sheet_commits_nothing_but_reports_every_row_synced() -> None:
    store = _CountingStore()
    rows = _students(20)
    run_sync(store, FakeSheet(rows))
    assert len(store.committed) == 20
    store.committed.clear()
    sheet = FakeSheet(rows)
    result = run_sync(store, sheet)
    assert store.committed == []
    assert result.status == "completed"
    assert result.versions_created == 0
    assert [o.status for o in sheet.writes[0]] == ["SYNCED"] * 20
    assert [o.version for o in sheet.writes[0]] == ["V1"] * 20


def test_only_the_student_who_changed_is_committed() -> None:
    store = _CountingStore()
    rows = _students(10)
    run_sync(store, FakeSheet(rows))
    store.committed.clear()
    rows.append({**rows[3], "skill": "SQL", "awarded_on": ""})
    sheet = FakeSheet(rows)
    result = run_sync(store, sheet)
    assert store.committed == ["s3@btu.edu.ge"]
    assert result.versions_created == 1
    by_index = {o.index: o for o in sheet.writes[0]}
    assert by_index[3].version == "V2"
    assert by_index[10].version == "V2"
    assert by_index[4].version == "V1"


def test_a_renamed_student_is_committed_even_when_the_skills_are_the_same() -> None:
    store = _CountingStore()
    rows = _students(3)
    run_sync(store, FakeSheet(rows))
    store.committed.clear()
    rows[1] = {**rows[1], "full_name": "Student One Renamed"}
    run_sync(store, FakeSheet(rows))
    assert store.committed == ["s1@btu.edu.ge"]
    assert [s.full_name for s in store.students if s.email == "s1@btu.edu.ge"] == [
        "Student One Renamed"
    ]


# --- sync: batched commits and the fallback -------------------------------------------------


def _unit(n: int) -> StudentUnit:
    skills = (Skill(skill="Python", badge="", awarded_on=None),)
    version = VersionRecord(
        passport_id=f"BTU-{n:010d}",
        email=f"s{n}@btu.edu.ge",
        version_number=1,
        holder_name=f"Student {n}",
        verification_code="AAAA-BBBB-CCCC-DDDD",
        verification_id_hash="0x" + "11" * 32,
        skill_fingerprint="f",
        content_hash="0x" + "22" * 32,
        anchor_status="pending",
        pdf_en_path=None,
        pdf_ka_path=None,
        tx_hash=None,
        issued_at="2026-10-31T11:00:00+00:00",
        skills=skills,
    )
    return StudentUnit(
        f"s{n}@btu.edu.ge", f"BTU-{n:010d}", f"Student {n}", False, 0, version, (f"k{n}",)
    )


_STORED = {
    "passport_id": "P",
    "version_number": 1,
    "created_student": True,
    "created_version": True,
}


class _Rpc:
    """A supabase client that records rpc calls, with a pluggable answer per function name."""

    def __init__(self, answers: dict[str, Callable[[dict[str, Any]], object]]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, int]] = []

    def rpc(self, name: str, params: dict[str, Any]) -> Any:
        size = len(params["p_units"]) if "p_units" in params else 1
        self.calls.append((name, size))

        def execute() -> _Result:
            return _Result(self.answers[name](params))

        return MagicMock(execute=execute)


def test_units_are_sent_in_batches_of_25_and_results_keep_their_order() -> None:
    def batch(params: dict[str, Any]) -> object:
        return [
            {"ok": True, "result": {**_STORED, "passport_id": u["email"]}}
            for u in params["p_units"]
        ]

    fake = _Rpc({"sync_student_units": batch})
    with patch("passport_api.sync.get_supabase", return_value=fake):
        outcomes = SupabaseSyncStore().commit_student_units([_unit(n) for n in range(60)])
    assert fake.calls == [
        ("sync_student_units", 25),
        ("sync_student_units", 25),
        ("sync_student_units", 10),
    ]
    assert [o.passport_id for o in outcomes if isinstance(o, UnitResult)] == [
        f"s{n}@btu.edu.ge" for n in range(60)
    ]


def test_a_failed_unit_in_a_batch_is_returned_as_its_own_error() -> None:
    def batch(params: dict[str, Any]) -> object:
        return [
            {"ok": True, "result": _STORED},
            {"ok": False, "code": "PS001", "message": "sync_unit_stale"},
            {"ok": True, "result": _STORED},
        ]

    fake = _Rpc({"sync_student_units": batch})
    with patch("passport_api.sync.get_supabase", return_value=fake):
        outcomes = SupabaseSyncStore().commit_student_units([_unit(n) for n in range(3)])
    assert [isinstance(o, Exception) for o in outcomes] == [False, True, False]
    assert isinstance(outcomes[1], APIError)
    assert outcomes[1].code == "PS001"


def test_without_migration_0012_units_are_committed_one_by_one_and_the_batch_is_not_retried() -> (
    None
):
    def missing(_params: dict[str, Any]) -> object:
        raise APIError({"code": "PGRST202", "message": "Could not find the function"})

    fake = _Rpc({"sync_student_units": missing, "sync_student_unit": lambda _p: _STORED})
    store = SupabaseSyncStore()
    with patch("passport_api.sync.get_supabase", return_value=fake):
        first = store.commit_student_units([_unit(n) for n in range(3)])
        second = store.commit_student_units([_unit(n) for n in range(3, 5)])
    assert all(isinstance(o, UnitResult) for o in first + second)
    assert fake.calls == [("sync_student_units", 3)] + [("sync_student_unit", 1)] * 5


def test_another_database_error_is_not_mistaken_for_a_missing_function() -> None:
    def refused(_params: dict[str, Any]) -> object:
        raise APIError({"code": "57014", "message": "statement timeout"})

    fake = _Rpc({"sync_student_units": refused, "sync_student_unit": lambda _p: _STORED})
    with patch("passport_api.sync.get_supabase", return_value=fake):
        outcomes = SupabaseSyncStore().commit_student_units([_unit(n) for n in range(2)])
    assert all(isinstance(o, APIError) for o in outcomes)
    assert fake.calls == [("sync_student_units", 2)]


def test_a_batch_answer_of_the_wrong_length_fails_every_unit_in_it() -> None:
    fake = _Rpc({"sync_student_units": lambda _p: [{"ok": True, "result": _STORED}]})
    with patch("passport_api.sync.get_supabase", return_value=fake):
        outcomes = SupabaseSyncStore().commit_student_units([_unit(n) for n in range(3)])
    assert len(outcomes) == 3
    assert all(isinstance(o, Exception) for o in outcomes)


# --- sync: reading more than one page of rows -----------------------------------------------


class _Pages:
    def __init__(self, total: int) -> None:
        self.rows = [{"passport_id": f"BTU-{i:06d}"} for i in range(total)]
        self.ranges: list[tuple[int, int]] = []

    def table(self, _name: str) -> "_Pages":
        return self

    def select(self, *_a: Any, **_k: Any) -> "_Pages":
        return self

    def order(self, *_a: Any, **_k: Any) -> "_Pages":
        return self

    def range(self, start: int, end: int) -> Any:
        # Like PostgREST: never more than 1000 rows however many were asked for.
        self.ranges.append((start, end))
        page = self.rows[start : min(end, start + 999) + 1]
        return MagicMock(execute=lambda: _Result(page))


@pytest.mark.parametrize(("total", "requests"), [(0, 1), (999, 1), (1000, 2), (2500, 3)])
def test_every_row_is_read_past_postgrests_1000_row_limit(total: int, requests: int) -> None:
    fake = _Pages(total)
    with patch("passport_api.sync.get_supabase", return_value=fake):
        ids = SupabaseSyncStore().taken_passport_ids()
    assert len(ids) == total
    assert len(fake.ranges) == requests


# --- sync: a Sheet that is already in sync costs no write -----------------------------------

HEADER = [
    "email",
    "full_name",
    "skill",
    "Passport Sync Status",
    "Synced Passport Version",
    "Synced At (UTC)",
    "Sync Error / Notes",
]


HEADER_ROW: list[object] = list(HEADER)


def _outcome(
    index: int, status: str = "SYNCED", version: str = "V1", error: str = ""
) -> RowOutcome:
    return RowOutcome(index, status, version, "2026-10-31 12:00 UTC", error, "")


def test_with_the_grid_as_read_only_changed_cells_are_written() -> None:
    grid: list[list[object]] = [
        HEADER_ROW,
        ["a@x", "A", "S", "SYNCED", "V1", "2026-10-30 09:00 UTC", ""],  # already in sync
        ["b@x", "B", "S", "", "", "", ""],  # never synced
        ["c@x", "C", "S", "FAILED", "V1", "2026-10-30 09:00 UTC", "sync_error"],  # now fixed
    ]
    updates = write_back_ranges(HEADER, 2, [_outcome(0), _outcome(1), _outcome(2)], current=grid)
    cells = {str(u["range"]) for u in updates}
    assert cells == {"D3", "E3", "F3", "D4", "F4", "G4"}
    # Row 2 (index 0) is untouched: not even its time stamp.
    assert not [c for c in cells if c.endswith("2")]
    # Row 3 changes status, version and time; the empty error cell already was empty.
    assert {"D3", "E3", "F3"} <= cells
    # Row 4 changes status and error, so the time is written with it, version is unchanged.
    assert {"D4", "F4", "G4"} == {c for c in cells if c.endswith("4")}


def test_without_the_grid_every_cell_is_written_as_before() -> None:
    updates = write_back_ranges(HEADER, 2, [_outcome(0)])
    assert [u["range"] for u in updates] == ["D2", "E2", "F2", "G2"]


def test_a_row_past_the_end_of_the_grid_is_written_whole() -> None:
    updates = write_back_ranges(HEADER, 5, [_outcome(0)], current=[HEADER_ROW])
    assert [u["range"] for u in updates] == ["D5", "E5", "F5"]


# --- sync: one open, one read request, one write request ------------------------------------


class _Worksheet:
    def __init__(self, title: str) -> None:
        self.title = title
        self.batches: list[list[dict[str, object]]] = []

    def batch_update(self, updates: list[dict[str, object]], value_input_option: str) -> None:
        assert value_input_option == "RAW"
        self.batches.append(updates)


class _Spreadsheet:
    def __init__(self, tabs: list[str], grids: list[list[list[object]]]) -> None:
        self.tabs = [_Worksheet(title) for title in tabs]
        self.grids = grids
        self.calls: list[str] = []

    def worksheets(self) -> list[_Worksheet]:
        self.calls.append("worksheets")
        return self.tabs

    def values_batch_get(self, names: list[str]) -> dict[str, Any]:
        self.calls.append("values_batch_get")
        self.names = names
        return {"valueRanges": [{"values": grid} for grid in self.grids]}


def test_one_run_opens_the_sheet_once_and_reads_both_tabs_in_one_request() -> None:
    grid: list[list[object]] = [HEADER_ROW, ["a@x", "A", "S", "", "", "", ""]]
    skills: list[list[object]] = [
        ["skill_id", "name_en", "category"],
        ["skl-1", "Python", "AI Skill"],
    ]
    spreadsheet = _Spreadsheet(["Data", "Skills"], [grid, skills])
    opened = MagicMock(return_value=spreadsheet)
    with patch("passport_api.sync.open_spreadsheet", opened):
        sheet = GspreadSheet()
        rows = sheet.read_rows()
        catalog = sheet.read_catalog()
        sheet.read_rows()
        sheet.write_back([_outcome(0)])
    assert opened.call_count == 1
    assert spreadsheet.calls == ["worksheets", "values_batch_get"]
    assert len(spreadsheet.names) == 2
    assert [r["email"] for r in rows] == ["a@x"]
    assert [skill.id for skill in catalog] == ["SKL-1"]
    assert len(spreadsheet.tabs[0].batches) == 1
    assert spreadsheet.tabs[1].batches == []


def test_without_a_skills_tab_only_the_first_tab_is_requested() -> None:
    spreadsheet = _Spreadsheet(["Data"], [[HEADER_ROW]])
    with patch("passport_api.sync.open_spreadsheet", return_value=spreadsheet):
        sheet = GspreadSheet()
        assert sheet.read_rows() == []
        assert sheet.read_catalog() == []
    assert len(spreadsheet.names) == 1


def test_a_sheet_that_is_already_in_sync_is_not_written_at_all() -> None:
    grid: list[list[object]] = [HEADER_ROW, ["a@x", "A", "S", "SYNCED", "V1", "t", ""]]
    spreadsheet = _Spreadsheet(["Data"], [grid])
    with patch("passport_api.sync.open_spreadsheet", return_value=spreadsheet):
        sheet = GspreadSheet()
        sheet.read_rows()
        sheet.write_back([_outcome(0)])
    assert spreadsheet.tabs[0].batches == []


def test_a_sheet_read_failure_is_reported_as_unavailable() -> None:
    spreadsheet = MagicMock()
    spreadsheet.worksheets.side_effect = RuntimeError("quota")
    with patch("passport_api.sync.open_spreadsheet", return_value=spreadsheet):
        with pytest.raises(sync_mod.SheetUnavailableError):
            GspreadSheet().read_rows()


# --- sync: PDFs for new versions are published side by side ---------------------------------


def test_new_pdfs_are_published_in_parallel_and_all_are_saved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    monkeypatch.setattr(settings, "pdf_storage_dir", str(tmp_path))
    lock = threading.Lock()
    running = [0]
    peak = [0]

    def slow_publish(document: Any, _storage: Any) -> tuple[str, str]:
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        time.sleep(0.05)
        with lock:
            running[0] -= 1
        return f"{document.passport_id}-en.pdf", f"{document.passport_id}-ka.pdf"

    monkeypatch.setattr(sync_mod, "publish_pdfs", slow_publish)
    store = MemorySyncStore()
    store.parallel_io = True  # type: ignore[attr-defined]
    run_sync(store, FakeSheet(_students(8)))
    assert peak[0] > 1
    assert all(v.pdf_en_path and v.pdf_ka_path for v in store.versions)
    assert len(store.versions) == 8


def test_one_failing_pdf_does_not_stop_the_others(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    monkeypatch.setattr(settings, "pdf_storage_dir", str(tmp_path))

    def publish(document: Any, _storage: Any) -> tuple[str, str]:
        if document.holder_name == "Student 1":
            raise RuntimeError("storage down")
        return "en.pdf", "ka.pdf"

    monkeypatch.setattr(sync_mod, "publish_pdfs", publish)
    store = MemorySyncStore()
    store.parallel_io = True  # type: ignore[attr-defined]
    result = run_sync(store, FakeSheet(_students(4)))
    assert result.status == "completed"
    with_pdf = sorted(v.holder_name for v in store.versions if v.pdf_en_path)
    assert with_pdf == ["Student 0", "Student 2", "Student 3"]
