"""One behaviour spec, run against both flag stores.

The memory store backs demos and the other tests. The Supabase store backs production. If they
disagree, a test that passes on memory says nothing about production, so every rule below must
hold for both."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fake_supabase import FakeSupabase

import passport_api.flags as flags_mod
from passport_api.errors import APIError
from passport_api.flags import FlagStore, MemoryFlagStore, SupabaseFlagStore

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


@pytest.fixture(params=["memory", "supabase"])
def store(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[FlagStore]:
    if request.param == "memory":
        yield MemoryFlagStore()
        return
    fake = FakeSupabase()
    monkeypatch.setattr(flags_mod, "get_supabase", lambda: fake)
    yield SupabaseFlagStore()


def add(store: FlagStore, *, version: int = 1, email: str = "s@btu.edu.ge", pid: str = "P1") -> Any:
    return store.create(
        passport_id=pid,
        version=version,
        verification_code="AAAA-BBBB-CCCC-DDDD",
        student_email=email,
        comment="Something looks wrong here.",
    )


def close(store: FlagStore, flag_id: str, status: Any = "resolved", note: str = "Fixed.") -> Any:
    return store.close(
        flag_id, status=status, admin_note=note, admin_email="admin@btu.edu.ge", when=NOW
    )


def test_a_new_flag_is_open_and_unread_does_not_apply_yet(store: FlagStore) -> None:
    flag = add(store)
    assert (flag.status, flag.admin_note, flag.resolved_by, flag.resolved_at) == (
        "open",
        "",
        None,
        None,
    )
    assert flag.unread is False
    assert store.has_open("P1", 1) is True
    assert store.has_open("P1", 2) is False
    assert store.has_open("P2", 1) is False


def test_a_second_open_flag_for_the_same_version_is_a_409(store: FlagStore) -> None:
    add(store)
    with pytest.raises(APIError) as caught:
        add(store)
    assert (caught.value.status_code, caught.value.code) == (409, "flag_already_open")


def test_a_closed_flag_does_not_block_a_new_one(store: FlagStore) -> None:
    first = add(store)
    close(store, first.id)
    second = add(store)
    assert second.id != first.id
    assert store.has_open("P1", 1) is True


def test_other_versions_and_students_can_flag_at_the_same_time(store: FlagStore) -> None:
    add(store, version=1)
    add(store, version=2)
    add(store, pid="P2", email="t@btu.edu.ge")
    assert store.open_count() == 3


def test_close_records_who_when_and_the_note_and_makes_it_unread(store: FlagStore) -> None:
    flag = add(store)
    closed = close(store, flag.id, "dismissed", "Not an issue.")
    assert closed is not None
    assert (closed.status, closed.admin_note, closed.resolved_by) == (
        "dismissed",
        "Not an issue.",
        "admin@btu.edu.ge",
    )
    assert closed.resolved_at is not None
    assert closed.unread is True
    assert store.has_open("P1", 1) is False


def test_closing_an_unknown_flag_returns_none(store: FlagStore) -> None:
    assert close(store, "does-not-exist") is None
    assert store.get("does-not-exist") is None


def test_get_returns_the_stored_flag(store: FlagStore) -> None:
    flag = add(store)
    found = store.get(flag.id)
    assert found is not None and found.id == flag.id and found.comment == flag.comment


def test_a_student_sees_only_their_own_flags_newest_first(store: FlagStore) -> None:
    older = add(store, version=1)
    newer = add(store, version=2)
    add(store, email="other@btu.edu.ge", pid="P2")
    mine = store.for_student("s@btu.edu.ge")
    assert [flag.id for flag in mine] == [newer.id, older.id]
    assert store.for_student("nobody@btu.edu.ge") == []


def test_mark_seen_touches_only_answered_flags_of_that_student(store: FlagStore) -> None:
    answered = add(store, version=1)
    still_open = add(store, version=2)
    someone_else = add(store, email="o@btu.edu.ge", pid="P2")
    close(store, answered.id)
    close(store, someone_else.id)
    store.mark_seen("s@btu.edu.ge", NOW)
    by_id = {flag.id: flag for flag in store.for_student("s@btu.edu.ge")}
    assert by_id[answered.id].unread is False
    assert by_id[still_open.id].student_seen_at is None
    other = store.get(someone_else.id)
    assert other is not None and other.unread is True


def test_a_new_reply_after_seen_is_unread_again(store: FlagStore) -> None:
    flag = add(store)
    close(store, flag.id)
    store.mark_seen("s@btu.edu.ge", NOW)
    again = close(store, flag.id, "dismissed", "Changed my mind.")
    assert again is not None and again.unread is True


def test_listing_filters_by_status_newest_first(store: FlagStore) -> None:
    first = add(store, version=1)
    second = add(store, version=2)
    third = add(store, version=3)
    close(store, first.id)
    assert [f.id for f in store.listing(None)] == [third.id, second.id, first.id]
    assert [f.id for f in store.listing("open")] == [third.id, second.id]
    assert [f.id for f in store.listing("resolved")] == [first.id]
    assert store.listing("dismissed") == []


def test_open_count_counts_only_open_flags(store: FlagStore) -> None:
    first = add(store, version=1)
    add(store, version=2)
    assert store.open_count() == 2
    close(store, first.id)
    assert store.open_count() == 1


def test_count_since_counts_a_students_recent_flags(store: FlagStore) -> None:
    for version in range(1, 4):
        add(store, version=version)
    add(store, email="other@btu.edu.ge", pid="P2")
    assert store.count_since("s@btu.edu.ge", NOW - timedelta(days=1)) == 3
    assert store.count_since("s@btu.edu.ge", NOW + timedelta(days=1)) == 0
    assert store.count_since("nobody@btu.edu.ge", NOW - timedelta(days=1)) == 0
