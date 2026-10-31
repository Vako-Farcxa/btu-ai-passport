"""The sync checks what it reads from the Sheet instead of guessing: a mistyped date, a name
that is not a name and an impossible passport ID become a named error on the row, never a
silently changed passport."""

import pytest

from passport_api.sync import FakeSheet, MemorySyncStore, run_sync
from passport_api.validation import full_name_error, passport_id_error


def row(
    email: str = "ada@btu.edu.ge",
    name: str = "Ada Lovelace",
    skill: str = "Python",
    awarded_on: str = "2026-09-18",
    passport_id: str = "",
) -> dict[str, str]:
    return {
        "email": email,
        "full_name": name,
        "skill": skill,
        "badge": "BDG-AI-001",
        "awarded_on": awarded_on,
        "passport_id": passport_id,
    }


def sync(store: MemorySyncStore, rows: list[dict[str, str]]) -> dict[int, tuple[str, str]]:
    sheet = FakeSheet(rows)
    run_sync(store, sheet)
    return {o.index: (o.status, o.error) for o in sheet.writes[-1]}


# -- the validators ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["Ada Lovelace", "Nino Beridze-Kapanadze", "O'Brien Sean", "გიორგი ბერიძე", "Zoë Müller"],
)
def test_real_names_pass(name: str) -> None:
    assert full_name_error(name) is None


@pytest.mark.parametrize(
    "name", ["1 1", "Student 7", "A", "", "  ", "Ada  --  Lovelace", "ada@btu.edu.ge", "x" * 102]
)
def test_things_that_are_not_names_fail(name: str) -> None:
    assert full_name_error(name) == "invalid_full_name"


def test_a_name_is_cleaned_before_it_is_checked() -> None:
    assert full_name_error("  Ada \t Lovelace ") is None


@pytest.mark.parametrize("value", ["BTU-AI-000125", "BTU-0123456789", "BTU-00000000AA", "ABCD"])
def test_plausible_passport_ids_pass(value: str) -> None:
    assert passport_id_error(value) is None


@pytest.mark.parametrize("value", ["", "btu-ai-1", "BTU AI 1", "-BTU", "AB", "BTU/../1", "A" * 41])
def test_impossible_passport_ids_fail(value: str) -> None:
    assert passport_id_error(value) == "invalid_passport_id"


# -- dates ------------------------------------------------------------------------------


def test_a_mistyped_date_fails_the_row_and_nothing_is_stored() -> None:
    store = MemorySyncStore()
    outcome = sync(store, [row(awarded_on="2026-13-45")])
    assert outcome == {0: ("FAILED", "invalid_awarded_on")}
    assert store.students == [] and store.versions == []


@pytest.mark.parametrize("typed", ["soon", "18/09/2026", "2026-9-18", "2026-02-30", "yesterday"])
def test_dates_that_are_not_iso_dates_are_all_refused(typed: str) -> None:
    store = MemorySyncStore()
    assert sync(store, [row(awarded_on=typed)])[0] == ("FAILED", "invalid_awarded_on")


def test_an_empty_date_is_still_allowed_it_means_no_date() -> None:
    store = MemorySyncStore()
    assert sync(store, [row(awarded_on="")]) == {0: ("SYNCED", "")}
    assert store.versions[0].skills[0].awarded_on is None


def test_one_bad_date_holds_back_the_whole_student_and_says_which_row() -> None:
    store = MemorySyncStore()
    rows = [row(skill="Python"), row(skill="SQL", awarded_on="soon"), row(skill="Rust")]
    assert sync(store, rows) == {
        0: ("FAILED", "other_row_invalid"),
        1: ("FAILED", "invalid_awarded_on"),
        2: ("FAILED", "other_row_invalid"),
    }
    assert store.versions == []


def test_other_students_still_sync_when_one_student_has_a_bad_date() -> None:
    store = MemorySyncStore()
    rows = [row(awarded_on="soon"), row(email="bob@btu.edu.ge", name="Bob Stone")]
    assert sync(store, rows) == {0: ("FAILED", "invalid_awarded_on"), 1: ("SYNCED", "")}
    assert [s.email for s in store.students] == ["bob@btu.edu.ge"]


def test_a_date_typed_wrongly_later_never_changes_the_passport_the_student_has() -> None:
    store = MemorySyncStore()
    sync(store, [row()])
    before = store.versions[0]
    assert sync(store, [row(), row(skill="SQL", awarded_on="soon")])[1][1] == "invalid_awarded_on"
    assert store.versions == [before]


def test_fixing_the_date_lets_the_student_through() -> None:
    store = MemorySyncStore()
    assert sync(store, [row(awarded_on="soon")])[0][0] == "FAILED"
    assert sync(store, [row(awarded_on="2026-09-18")])[0] == ("SYNCED", "")
    assert len(store.versions) == 1


# -- names ------------------------------------------------------------------------------


def test_a_new_student_needs_a_real_name() -> None:
    store = MemorySyncStore()
    outcome = sync(store, [row(name="1 1")])
    assert outcome == {0: ("FAILED", "invalid_full_name")}
    assert store.students == []


def test_a_rename_to_something_that_is_not_a_name_is_refused_and_changes_nothing() -> None:
    store = MemorySyncStore()
    sync(store, [row()])
    outcome = sync(store, [row(name="Student 9"), row(name="Student 9", skill="SQL")])
    assert outcome[0] == ("FAILED", "invalid_full_name")
    assert store.students[0].full_name == "Ada Lovelace"
    assert len(store.versions) == 1


def test_a_student_whose_stored_name_is_odd_keeps_syncing_while_the_sheet_leaves_it_alone() -> None:
    store = MemorySyncStore()
    sync(store, [row(name="Ada Lovelace")])
    store.students[0] = type(store.students[0])(
        **{**store.students[0].__dict__, "full_name": "Old Name 2"}
    )
    outcome = sync(store, [row(name="Old Name 2"), row(name="Old Name 2", skill="SQL")])
    assert outcome == {0: ("SYNCED", ""), 1: ("SYNCED", "")}
    assert len(store.versions) == 2


def test_a_blank_name_on_an_existing_student_is_fine() -> None:
    store = MemorySyncStore()
    sync(store, [row()])
    assert sync(store, [row(name="")]) == {0: ("SYNCED", "")}
    assert len(store.versions) == 1


# -- passport ids -----------------------------------------------------------------------


def test_a_new_student_with_an_impossible_passport_id_is_refused() -> None:
    store = MemorySyncStore()
    assert sync(store, [row(passport_id="not an id!")]) == {0: ("FAILED", "invalid_passport_id")}
    assert store.students == []


def test_a_valid_typed_passport_id_is_kept() -> None:
    store = MemorySyncStore()
    assert sync(store, [row(passport_id="btu-ai-000125")])[0][0] == "SYNCED"
    assert store.students[0].passport_id == "BTU-AI-000125"
