"""The numbers on the admin dashboard, read with as few round trips as possible.

The dashboard used to load 100 students with every version nested inside, only to read
`total` and count the admin-managed ones in the browser, then ask separately for pending
anchors, flags and sync runs. `load_admin_stats` returns all of it from one request:

- with migration 0012, one call to `admin_dashboard_stats()` (a few indexed counts);
- without it, the same counts as separate head-only queries, run side by side.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any, Literal, cast

from postgrest import CountMethod

from passport_api.db import get_supabase
from passport_api.schemas import AdminStats, AdminSyncRun

# Anchor statuses that still mean "being worked on" (see store.normalize_anchor_status).
_WORKING = ("confirmed", "pending", "retrying", "failed")
_RUN_COLUMNS = "id, status, started_at, finished_at, rows_read, versions_created, error"


def _datetime(value: object) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _optional_int(value: object) -> int | None:
    return None if value is None else int(cast(int, value))


def sync_run_from_row(row: dict[str, Any]) -> AdminSyncRun:
    finished = row.get("finished_at")
    return AdminSyncRun(
        id=cast(str, row["id"]),
        status=cast(Literal["running", "completed", "skipped", "failed"], row["status"]),
        started_at=_datetime(row.get("started_at") or datetime.now(UTC).isoformat()),
        finished_at=None if finished is None else _datetime(finished),
        rows_read=_optional_int(row.get("rows_read")),
        versions_created=_optional_int(row.get("versions_created")),
        error=None if row.get("error") is None else str(row["error"]),
    )


def _rows(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [cast(dict[str, Any], row) for row in value if isinstance(row, dict)]


def load_admin_stats() -> AdminStats:
    db = get_supabase()
    data = _from_function(db)
    if data is None:
        data = _from_counts(db)
    return AdminStats(
        total_students=int(data["total_students"]),
        admin_managed_students=int(data["admin_managed_students"]),
        pending_anchors=int(data["pending_anchors"]),
        failed_anchors=int(data["failed_anchors"]),
        open_flags=int(data["open_flags"]),
        recent_runs=[sync_run_from_row(row) for row in _rows(data["recent_runs"])],
    )


def _from_function(db: Any) -> dict[str, Any] | None:
    try:
        data = db.rpc("admin_dashboard_stats").execute().data
    except Exception:
        # Migration 0012 is not applied (or the call failed): count the old way.
        return None
    if not isinstance(data, dict) or "total_students" not in data:
        return None
    return cast(dict[str, Any], data)


def _count(query: Any) -> int:
    return int(query.limit(1).execute().count or 0)


def _from_counts(db: Any) -> dict[str, Any]:
    def table(name: str) -> Any:
        return db.table(name).select("id", count=CountMethod.exact)

    jobs = {
        "total_students": lambda: _count(table("students").is_("deleted_at", "null")),
        "admin_managed_students": lambda: _count(
            table("students").is_("deleted_at", "null").eq("admin_managed", True)
        ),
        "pending_anchors": lambda: _count(
            table("passport_versions").neq("anchor_status", "confirmed")
        ),
        "failed_anchors": lambda: _count(
            table("passport_versions").not_.in_("anchor_status", list(_WORKING))
        ),
        "open_flags": lambda: _count(table("flags").eq("status", "open")),
        "recent_runs": lambda: (
            db.table("sync_runs")
            .select(_RUN_COLUMNS)
            .order("started_at", desc=True)
            .limit(5)
            .execute()
            .data
        ),
    }
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {name: pool.submit(job) for name, job in jobs.items()}
        return {name: future.result() for name, future in futures.items()}
