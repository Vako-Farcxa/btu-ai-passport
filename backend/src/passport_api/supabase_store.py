from typing import cast

from passport_api.db import get_supabase
from passport_api.schemas import Skill
from passport_api.store import AnchorStatus, StoredVersion


class SupabaseStore:
    """Reads issued versions. Used only when Supabase credentials are set."""

    def find(self, code: str) -> StoredVersion | None:
        normalized = code.strip().upper()
        response = (
            get_supabase()
            .table("passport_versions")
            .select(
                "student_id, version_number, holder_name, verification_code, "
                "anchor_status, tx_hash, skill_entries(skill, badge, awarded_on, position), "
                "students(email, full_name, passport_id)"
            )
            .eq("verification_code", normalized)
            .limit(1)
            .execute()
        )
        rows = cast(list[dict[str, object]], response.data)
        if not rows:
            return None
        return _version_from_row(rows[0])

    def max_version(self, passport_id: str) -> int:
        response = (
            get_supabase()
            .table("students")
            .select("id, passport_versions(version_number)")
            .eq("passport_id", passport_id)
            .limit(1)
            .execute()
        )
        rows = cast(list[dict[str, object]], response.data)
        if not rows:
            raise KeyError(passport_id)
        versions = cast(list[dict[str, object]], rows[0]["passport_versions"])
        return max(int(cast(int, version["version_number"])) for version in versions)


def _anchor_status(value: str) -> AnchorStatus:
    if value == "pending":
        return "pending"
    if value == "confirmed":
        return "confirmed"
    return "failed"


def _version_from_row(row: dict[str, object]) -> StoredVersion:
    student = cast(dict[str, object], row["students"])
    skill_rows = cast(list[dict[str, object]], row["skill_entries"])
    ordered = sorted(skill_rows, key=lambda item: int(cast(int, item["position"])))
    skills = tuple(
        Skill(
            skill=str(item["skill"]),
            badge=str(item["badge"]),
            awarded_on=None if item["awarded_on"] is None else str(item["awarded_on"]),
        )
        for item in ordered
    )
    tx_hash = row["tx_hash"]
    return StoredVersion(
        passport_id=str(student["passport_id"]),
        email=str(student["email"]),
        full_name=str(student["full_name"]),
        version=int(cast(int, row["version_number"])),
        holder_name=str(row["holder_name"]),
        verification_code=str(row["verification_code"]),
        anchor_status=_anchor_status(str(row["anchor_status"])),
        tx_hash=None if tx_hash is None else str(tx_hash),
        skills=skills,
    )
