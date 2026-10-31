"""The default award date is the day in Tbilisi (UTC+4, no daylight saving)."""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from test_admin_skills import FakeAdminSheet, FakeDb, existing_row, seed_skill

import passport_api.api.admin as admin_mod
import passport_api.clock as clock
from passport_api.api.admin import get_admin_sheet
from passport_api.api.sync import get_sync_store
from passport_api.clock import local_today
from passport_api.main import app
from passport_api.sync import MemorySyncStore


@pytest.mark.parametrize(
    ("utc_moment", "expected"),
    [
        # 21:30 UTC is already 01:30 the next day in Tbilisi.
        (datetime(2026, 10, 28, 21, 30, tzinfo=UTC), date(2026, 10, 29)),
        (datetime(2026, 10, 28, 19, 59, 59, tzinfo=UTC), date(2026, 10, 28)),
        (datetime(2026, 10, 28, 20, 0, tzinfo=UTC), date(2026, 10, 29)),
        (datetime(2026, 12, 31, 20, 30, tzinfo=UTC), date(2027, 1, 1)),
        # July has no daylight saving in Georgia: the offset is still +4.
        (datetime(2026, 7, 1, 20, 0, tzinfo=UTC), date(2026, 7, 2)),
    ],
)
def test_the_date_is_the_tbilisi_day(utc_moment: datetime, expected: date) -> None:
    assert local_today(utc_moment) == expected


def test_a_time_given_in_another_zone_is_converted() -> None:
    new_york_evening = datetime(2026, 10, 28, 18, 0, tzinfo=timezone(timedelta(hours=-4)))
    assert local_today(new_york_evening) == date(2026, 10, 29)


def test_a_time_without_a_zone_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        local_today(datetime(2026, 10, 28, 12, 0))


def test_an_award_without_a_date_uses_the_tbilisi_day(monkeypatch: pytest.MonkeyPatch) -> None:
    db, sheet, store = FakeDb(), FakeAdminSheet([existing_row()]), MemorySyncStore()
    seed_skill(db)
    monkeypatch.setattr(admin_mod, "require_admin", lambda _auth: "admin@btu.edu.ge")
    monkeypatch.setattr(admin_mod, "get_supabase", lambda: db)
    monkeypatch.setattr(clock, "now_utc", lambda: datetime(2026, 10, 28, 22, 15, tzinfo=UTC))
    app.dependency_overrides[get_admin_sheet] = lambda: sheet
    app.dependency_overrides[get_sync_store] = lambda: store
    try:
        response = TestClient(app).post(
            "/admin/awards",
            headers={"Authorization": "Bearer x"},
            json={
                "skill_id": "SKL-002",
                "students": [
                    {"email": "nino@btu.edu.ge", "first_name": "Nino", "last_name": "Beridze"}
                ],
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    header = sheet.grid[3]
    new_row = dict(zip(header, sheet.grid[-1], strict=True))
    assert new_row["BTU Email (Test)"] == "nino@btu.edu.ge"
    assert new_row["Date Earned"] == "2026-10-29"
