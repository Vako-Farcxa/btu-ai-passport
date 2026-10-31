"""What the admin dashboard banner shows: the things that need a person's attention.

`evaluate` is a pure function over rows already read from the database, so every rule can be
tested without one. `load_admin_health` reads the rows (four small read-only queries) and
calls it.

Rules, each one an alert with a severity (warning = amber, critical = red):

- the last finished sync failed (critical, with the stored reason code),
- no sync has completed for more than 60 minutes (warning, critical after 3 hours); the sync
  cron runs every 15 minutes, so an hour of silence means it is not running or always failing,
- an anchor is failed_permanent (critical, an admin has to act),
- an anchor has been pending or retrying for more than 60 minutes (warning),
- the database consistency report lists problems, or could not be produced (warning).

"Skipped" syncs (another run was in progress) and a sync that is still running are ignored.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from passport_api.db import get_supabase
from passport_api.schemas import AdminHealth, HealthAlert
from passport_api.store import normalize_anchor_status

SYNC_STALE_AFTER = timedelta(minutes=60)
SYNC_CRITICAL_AFTER = timedelta(hours=3)
ANCHOR_STUCK_AFTER = timedelta(minutes=60)
_REASON_MAX = 120


def _when(value: object) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _minutes(delta: timedelta) -> int:
    return int(delta.total_seconds() // 60)


def _duration(delta: timedelta) -> str:
    minutes = _minutes(delta)
    if minutes < 120:
        return f"{minutes} minutes"
    return f"{minutes // 60} hours"


def evaluate(
    *,
    now: datetime,
    last_finished_run: Mapping[str, Any] | None,
    last_success_run: Mapping[str, Any] | None,
    open_versions: Sequence[Mapping[str, Any]],
    inconsistencies: int | None,
) -> AdminHealth:
    alerts: list[HealthAlert] = []

    last_status: str | None = None
    last_error: str | None = None
    last_at: datetime | None = None
    if last_finished_run is not None:
        last_status = str(last_finished_run["status"])
        last_at = _when(last_finished_run.get("finished_at") or last_finished_run.get("started_at"))
        raw_error = last_finished_run.get("error")
        last_error = None if raw_error is None else str(raw_error)[:_REASON_MAX]
    if last_status == "failed":
        alerts.append(
            HealthAlert(
                code="sync_failed",
                severity="critical",
                message="The last sync failed.",
                reason=last_error or "unknown",
            )
        )

    success_at = (
        None
        if last_success_run is None
        else _when(last_success_run.get("finished_at") or last_success_run.get("started_at"))
    )
    if success_at is None:
        alerts.append(
            HealthAlert(
                code="sync_never_succeeded",
                severity="warning",
                message="No sync has completed yet.",
            )
        )
    else:
        age = now - success_at
        if age > SYNC_STALE_AFTER:
            alerts.append(
                HealthAlert(
                    code="sync_stale",
                    severity="critical" if age > SYNC_CRITICAL_AFTER else "warning",
                    message=f"No sync has completed for {_duration(age)}. It should run every "
                    "15 minutes.",
                )
            )

    failed_permanent = 0
    stuck = 0
    stuck_reason: str | None = None
    stuck_oldest: datetime | None = None
    for row in open_versions:
        anchor = normalize_anchor_status(str(row["anchor_status"]))
        if anchor == "confirmed":
            continue
        if anchor == "failed_permanent":
            failed_permanent += 1
            continue
        issued = _when(row.get("issued_at"))
        submitted = _when(row.get("anchor_submitted_at"))
        started = max((t for t in (issued, submitted) if t is not None), default=None)
        if started is None or now - started <= ANCHOR_STUCK_AFTER:
            continue
        stuck += 1
        if stuck_oldest is None or started < stuck_oldest:
            stuck_oldest = started
            error = row.get("anchor_last_error")
            stuck_reason = None if error is None else str(error)[:_REASON_MAX]
    if failed_permanent:
        alerts.append(
            HealthAlert(
                code="anchors_failed_permanent",
                severity="critical",
                message=f"{failed_permanent} passport "
                f"{'version needs' if failed_permanent == 1 else 'versions need'} manual "
                "attention: anchoring gave up.",
                count=failed_permanent,
            )
        )
    if stuck and stuck_oldest is not None:
        alerts.append(
            HealthAlert(
                code="anchors_stuck",
                severity="warning",
                message=f"{stuck} passport {'version has' if stuck == 1 else 'versions have'} "
                f"been waiting for blockchain anchoring for over {_duration(ANCHOR_STUCK_AFTER)} "
                f"(oldest {_duration(now - stuck_oldest)}).",
                reason=stuck_reason,
                count=stuck,
            )
        )

    if inconsistencies is None:
        alerts.append(
            HealthAlert(
                code="consistency_check_failed",
                severity="warning",
                message="The database consistency check could not run.",
            )
        )
    elif inconsistencies > 0:
        alerts.append(
            HealthAlert(
                code="inconsistencies",
                severity="warning",
                message=f"The database consistency check found {inconsistencies} "
                f"{'problem' if inconsistencies == 1 else 'problems'}.",
                count=inconsistencies,
            )
        )

    alerts.sort(key=lambda alert: alert.severity != "critical")
    status = (
        "critical"
        if any(a.severity == "critical" for a in alerts)
        else "warning"
        if alerts
        else "ok"
    )
    return AdminHealth(
        status=status,
        checked_at=now,
        alerts=alerts,
        last_sync_status=cast(Any, last_status),
        last_sync_error=last_error,
        last_sync_at=last_at,
        last_success_at=success_at,
        anchors_failed_permanent=failed_permanent,
        anchors_stuck=stuck,
        inconsistencies=inconsistencies,
    )


def _rows(data: object) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        return []
    return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]


def load_admin_health(now: datetime | None = None) -> AdminHealth:
    """Read the rows and evaluate them. A failing database read raises; the caller reports it."""
    db = get_supabase()
    runs = (
        db.table("sync_runs")
        .select("status, started_at, finished_at, error")
        .in_("status", ["completed", "failed"])
        .order("started_at", desc=True)
        .limit(1)
        .execute()
    )
    success = (
        db.table("sync_runs")
        .select("status, started_at, finished_at, error")
        .eq("status", "completed")
        .order("started_at", desc=True)
        .limit(1)
        .execute()
    )
    versions = (
        db.table("passport_versions")
        .select("anchor_status, issued_at, anchor_submitted_at, anchor_last_error")
        .neq("anchor_status", "confirmed")
        .execute()
    )
    try:
        inconsistencies: int | None = len(_rows(db.rpc("sync_inconsistencies").execute().data))
    except Exception:
        # For example migration 0011 is not applied. The banner says the check could not run.
        inconsistencies = None
    last_runs = _rows(runs.data)
    last_success = _rows(success.data)
    return evaluate(
        now=now or datetime.now(UTC),
        last_finished_run=last_runs[0] if last_runs else None,
        last_success_run=last_success[0] if last_success else None,
        open_versions=_rows(versions.data),
        inconsistencies=inconsistencies,
    )
