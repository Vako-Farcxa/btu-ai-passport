"""GET /admin/health: the rules behind the dashboard banner."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

import passport_api.admin_health as admin_health
import passport_api.api.admin as admin_mod
from passport_api.admin_health import evaluate
from passport_api.main import app

client = TestClient(app)
NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


def _run(minutes_ago: int, status: str = "completed", error: str | None = None) -> dict[str, Any]:
    finished = NOW - timedelta(minutes=minutes_ago)
    return {
        "status": status,
        "started_at": (finished - timedelta(seconds=20)).isoformat(),
        "finished_at": finished.isoformat(),
        "error": error,
    }


def _anchor(status: str, minutes_ago: int, **extra: Any) -> dict[str, Any]:
    return {
        "anchor_status": status,
        "issued_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
        "anchor_submitted_at": None,
        "anchor_last_error": None,
        **extra,
    }


def _health(
    *,
    last: dict[str, Any] | None = None,
    success: dict[str, Any] | None = None,
    versions: list[dict[str, Any]] | None = None,
    inconsistencies: int | None = 0,
) -> Any:
    good = _run(5)
    return evaluate(
        now=NOW,
        last_finished_run=good if last is None else last,
        last_success_run=good if success is None else success,
        open_versions=versions or [],
        inconsistencies=inconsistencies,
    )


def _codes(health: Any) -> list[str]:
    return [alert.code for alert in health.alerts]


def test_all_quiet_is_ok() -> None:
    health = _health(versions=[_anchor("pending", 5)])
    assert health.status == "ok"
    assert health.alerts == []
    assert health.last_sync_status == "completed"
    assert health.inconsistencies == 0


def test_a_failed_last_sync_is_red_with_its_reason_code() -> None:
    health = _health(last=_run(2, "failed", "sheet_unavailable"), success=_run(20))
    assert health.status == "critical"
    alert = health.alerts[0]
    assert (alert.code, alert.severity, alert.reason) == (
        "sync_failed",
        "critical",
        "sheet_unavailable",
    )
    assert health.last_sync_error == "sheet_unavailable"
    assert health.last_sync_status == "failed"


def test_a_failed_sync_without_a_reason_says_unknown() -> None:
    health = _health(last=_run(2, "failed"), success=_run(20))
    assert health.alerts[0].reason == "unknown"


def test_no_sync_for_over_an_hour_is_amber() -> None:
    quiet = _health(success=_run(60))
    assert quiet.alerts == []
    health = _health(last=_run(61), success=_run(61))
    assert health.status == "warning"
    assert _codes(health) == ["sync_stale"]
    assert "61 minutes" in health.alerts[0].message


def test_no_sync_for_hours_turns_red() -> None:
    health = _health(last=_run(200), success=_run(200))
    assert health.status == "critical"
    assert health.alerts[0].code == "sync_stale"
    assert "3 hours" in health.alerts[0].message


def test_a_failing_sync_that_was_fine_a_while_ago_shows_both() -> None:
    health = _health(last=_run(1, "failed", "sync_failed"), success=_run(90))
    assert _codes(health) == ["sync_failed", "sync_stale"]
    assert health.status == "critical"


def test_never_synced_is_amber() -> None:
    health = evaluate(
        now=NOW, last_finished_run=None, last_success_run=None, open_versions=[], inconsistencies=0
    )
    assert health.status == "warning"
    assert _codes(health) == ["sync_never_succeeded"]
    assert health.last_sync_status is None


def test_a_failed_permanent_anchor_is_red() -> None:
    health = _health(versions=[_anchor("failed_permanent", 5), _anchor("failed_permanent", 500)])
    assert health.status == "critical"
    assert health.alerts[0].code == "anchors_failed_permanent"
    assert health.alerts[0].count == 2
    assert health.anchors_failed_permanent == 2


def test_an_anchor_open_for_over_an_hour_is_amber() -> None:
    fresh = _anchor("retrying", 59)
    old = _anchor("retrying", 120, anchor_last_error="rpc_unreachable")
    older_pending = _anchor("pending", 300)
    health = _health(versions=[fresh, old, older_pending])
    assert health.status == "warning"
    alert = health.alerts[0]
    assert alert.code == "anchors_stuck"
    assert alert.count == 2
    assert health.anchors_stuck == 2
    assert "oldest 5 hours" in alert.message


def test_the_stuck_reason_is_the_oldest_ones_stored_code() -> None:
    health = _health(
        versions=[
            _anchor("retrying", 100, anchor_last_error="insufficient_funds"),
            _anchor("retrying", 400, anchor_last_error="rpc_unreachable"),
        ]
    )
    assert health.alerts[0].reason == "rpc_unreachable"


def test_a_recent_broadcast_resets_the_stuck_clock() -> None:
    # An admin retry of an old version broadcast a new transaction a minute ago.
    retried = _anchor(
        "pending",
        5000,
        anchor_submitted_at=(NOW - timedelta(minutes=1)).isoformat(),
    )
    assert _health(versions=[retried]).alerts == []


def test_the_legacy_failed_status_counts_as_retrying() -> None:
    health = _health(versions=[_anchor("failed", 200)])
    assert _codes(health) == ["anchors_stuck"]


def test_consistency_problems_are_amber_with_a_count() -> None:
    health = _health(inconsistencies=3)
    assert health.status == "warning"
    assert (health.alerts[0].code, health.alerts[0].count) == ("inconsistencies", 3)
    assert health.inconsistencies == 3


def test_a_consistency_check_that_could_not_run_is_amber() -> None:
    health = _health(inconsistencies=None)
    assert _codes(health) == ["consistency_check_failed"]
    assert health.inconsistencies is None


def test_red_alerts_come_first() -> None:
    health = _health(
        inconsistencies=1,
        versions=[_anchor("failed_permanent", 1)],
    )
    assert _codes(health) == ["anchors_failed_permanent", "inconsistencies"]


# -- the endpoint ---------------------------------------------------------------------


class _Result:
    def __init__(self, data: object) -> None:
        self.data = data


class _Query:
    def __init__(self, data: object, log: list[tuple[str, tuple[Any, ...]]]) -> None:
        self._data = data
        self._log = log

    def __getattr__(self, name: str) -> Any:
        def call(*args: Any, **_kwargs: Any) -> "_Query":
            self._log.append((name, args))
            return self

        return call

    def execute(self) -> _Result:
        return _Result(self._data)


class _FakeDb:
    def __init__(
        self, *, runs: list[Any], versions: list[Any], problems: list[Any] | Exception
    ) -> None:
        self.runs = runs
        self.versions = versions
        self.problems = problems
        self.log: list[tuple[str, tuple[Any, ...]]] = []

    def table(self, name: str) -> _Query:
        self.log.append(("table", (name,)))
        if name == "sync_runs":
            return _Query(self.runs, self.log)
        assert name == "passport_versions"
        return _Query(self.versions, self.log)

    def rpc(self, name: str) -> _Query:
        self.log.append(("rpc", (name,)))
        if isinstance(self.problems, Exception):
            raise self.problems
        return _Query(self.problems, self.log)


def _as_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin_mod, "require_admin", lambda _auth: "admin@btu.edu.ge")


def test_the_endpoint_reports_alerts(monkeypatch: pytest.MonkeyPatch) -> None:
    _as_admin(monkeypatch)
    now = datetime.now(UTC)
    failed = {
        "status": "failed",
        "started_at": (now - timedelta(minutes=2)).isoformat(),
        "finished_at": (now - timedelta(minutes=1)).isoformat(),
        "error": "sheet_unavailable",
    }
    fake = _FakeDb(
        runs=[failed],
        versions=[{**_anchor("failed_permanent", 5), "issued_at": now.isoformat()}],
        problems=[{"kind": "version_without_skills"}],
    )
    monkeypatch.setattr(admin_health, "get_supabase", lambda: fake)
    response = client.get("/admin/health", headers={"Authorization": "Bearer x"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "critical"
    codes = [alert["code"] for alert in body["alerts"]]
    assert codes[:2] == ["sync_failed", "anchors_failed_permanent"]
    assert "inconsistencies" in codes
    assert body["alerts"][0]["reason"] == "sheet_unavailable"
    assert body["inconsistencies"] == 1
    assert ("rpc", ("sync_inconsistencies",)) in fake.log
    # Read only: nothing but selects.
    assert not [name for name, _ in fake.log if name in {"insert", "update", "upsert", "delete"}]


def test_the_endpoint_is_ok_when_everything_is_fine(monkeypatch: pytest.MonkeyPatch) -> None:
    _as_admin(monkeypatch)
    now = datetime.now(UTC)
    done = {
        "status": "completed",
        "started_at": (now - timedelta(minutes=3)).isoformat(),
        "finished_at": (now - timedelta(minutes=2)).isoformat(),
        "error": None,
    }
    fake = _FakeDb(runs=[done], versions=[], problems=[])
    monkeypatch.setattr(admin_health, "get_supabase", lambda: fake)
    response = client.get("/admin/health", headers={"Authorization": "Bearer x"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["alerts"] == []


def test_a_missing_consistency_function_does_not_break_the_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _as_admin(monkeypatch)
    fake = _FakeDb(runs=[], versions=[], problems=RuntimeError("function does not exist"))
    monkeypatch.setattr(admin_health, "get_supabase", lambda: fake)
    response = client.get("/admin/health", headers={"Authorization": "Bearer x"})
    assert response.status_code == 200
    codes = [alert["code"] for alert in response.json()["alerts"]]
    assert "consistency_check_failed" in codes


def test_a_database_failure_is_a_503_without_details(monkeypatch: pytest.MonkeyPatch) -> None:
    _as_admin(monkeypatch)

    def broken() -> Any:
        raise RuntimeError("connection to https://secret.supabase.co refused")

    monkeypatch.setattr(admin_health, "get_supabase", broken)
    response = client.get("/admin/health", headers={"Authorization": "Bearer x"})
    assert response.status_code == 503
    assert response.json() == {"code": "health_unavailable"}


def test_the_endpoint_is_admin_only() -> None:
    assert client.get("/admin/health").status_code == 401
    response = client.get("/admin/health", headers={"Authorization": "Bearer nonsense"})
    assert response.status_code in (401, 403)
