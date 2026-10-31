"""The calendar day in Georgia, where BTU works. Georgia has no daylight saving time, so a
fixed UTC+4 offset is always right and needs no timezone database on the server."""

from datetime import UTC, date, datetime, timedelta, timezone

GEORGIA = timezone(timedelta(hours=4), "Asia/Tbilisi")


def now_utc() -> datetime:
    return datetime.now(UTC)


def local_today(now: datetime | None = None) -> date:
    """Today's date in Tbilisi. An award made at 23:30 in Tbilisi is dated that day, not the
    next one in UTC, and one made at 01:00 is not dated the day before."""
    moment = now or now_utc()
    if moment.tzinfo is None:
        raise ValueError("local_today needs a timezone-aware time")
    return moment.astimezone(GEORGIA).date()
