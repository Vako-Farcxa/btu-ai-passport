"""Find students and versions left half-written, without changing anything.

Before migration 0011 the sync wrote a student, its version and its skills as separate calls,
so a crash in between could leave:

- student_without_version: an active student with no passport version.
- version_without_skills: a version whose anchored hash cannot match its (empty) stored skills.
- skill_fingerprint_mismatch / content_hash_mismatch: stored skills that no longer hash to the
  stored hashes (the version was anchored with different content).
- version_number_gap / skill_position_gap: numbering that is not 1..n.

This is a report. A repair would change passport data that may already be anchored on-chain, so
it is left to a person (the admin fixes the Sheet; a version with wrong content is re-issued).
The structural checks are also available in SQL: `select * from sync_inconsistencies();`.
"""

from dataclasses import dataclass
from typing import Any, cast

from passport_api.db import get_supabase
from passport_api.schemas import Skill
from passport_api.sync import snapshot_problem

_PAGE = 500
_SELECT = (
    "email, passport_id, deleted_at, "
    "passport_versions(version_number, holder_name, skill_fingerprint, content_hash, "
    "skill_entries(skill, badge, awarded_on, description, skill_id, position))"
)


@dataclass(frozen=True)
class Inconsistency:
    kind: str
    passport_id: str
    version_number: int | None
    detail: str


def find_inconsistencies(students: list[dict[str, Any]]) -> list[Inconsistency]:
    """Problems in students rows shaped like `_SELECT` (versions and skill entries nested)."""
    found: list[Inconsistency] = []
    for student in students:
        passport_id = str(student["passport_id"])
        versions = _rows(student.get("passport_versions"))
        if not versions:
            if student.get("deleted_at") is None:
                found.append(
                    Inconsistency(
                        "student_without_version",
                        passport_id,
                        None,
                        "Active student with no passport version. The next sync creates version 1.",
                    )
                )
            continue
        numbers = [int(v["version_number"]) for v in versions]
        if max(numbers) != len(numbers):
            found.append(
                Inconsistency(
                    "version_number_gap",
                    passport_id,
                    None,
                    f"{len(numbers)} versions, highest is {max(numbers)}.",
                )
            )
        for version in sorted(versions, key=lambda v: int(v["version_number"])):
            found.extend(_version_problems(passport_id, version))
    return found


def _version_problems(passport_id: str, version: dict[str, Any]) -> list[Inconsistency]:
    number = int(version["version_number"])
    entries = sorted(_rows(version.get("skill_entries")), key=lambda e: int(e["position"]))
    if not entries:
        return [
            Inconsistency(
                "version_without_skills",
                passport_id,
                number,
                "No skill entries, so the anchored hash cannot match the stored content.",
            )
        ]
    found: list[Inconsistency] = []
    if [int(e["position"]) for e in entries] != list(range(1, len(entries) + 1)):
        found.append(
            Inconsistency(
                "skill_position_gap", passport_id, number, "Skill positions are not 1..n."
            )
        )
    skills = tuple(
        Skill(
            skill=str(e["skill"]),
            badge=str(e["badge"]),
            awarded_on=None if e.get("awarded_on") is None else str(e["awarded_on"]),
            description=str(e.get("description") or ""),
        )
        for e in entries
    )
    problem = snapshot_problem(
        holder_name=str(version["holder_name"]),
        passport_id=passport_id,
        version_number=number,
        skills=skills,
        skill_fingerprint_value=str(version["skill_fingerprint"]),
        content_hash_value=str(version["content_hash"]),
    )
    if problem is not None:
        found.append(
            Inconsistency(
                problem,
                passport_id,
                number,
                "Stored skills do not hash to the stored hash.",
            )
        )
    return found


def load_students() -> list[dict[str, Any]]:
    """Every student with versions and skills, read page by page (read only)."""
    students: list[dict[str, Any]] = []
    start = 0
    while True:
        response = (
            get_supabase()
            .table("students")
            .select(_SELECT)
            .order("id")
            .range(start, start + _PAGE - 1)
            .execute()
        )
        page = _rows(response.data)
        students.extend(page)
        if len(page) < _PAGE:
            return students
        start += _PAGE


def _rows(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [cast(dict[str, Any], row) for row in value if isinstance(row, dict)]
