from typing import cast

from passport_api.db import get_supabase
from passport_api.schemas import Skill
from passport_api.store import AnchorStatus, LatestVersion, StoredVersion, normalize_anchor_status


class SupabaseStore:
    """Reads issued versions. Used only when Supabase credentials are set."""

    def find(self, code: str) -> StoredVersion | None:
        normalized = code.strip().upper()
        response = (
            get_supabase()
            .table("passport_versions")
            .select(
                "student_id, version_number, holder_name, verification_code, "
                "anchor_status, tx_hash, issued_at, pdf_en_path, pdf_ka_path, revoked_at, "
                "content_hash, anchored_at, "
                "skill_entries(skill, badge, awarded_on, description, position), "
                "students(email, full_name, passport_id, deleted_at)"
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

    def latest_version(self, passport_id: str) -> LatestVersion:
        response = (
            get_supabase()
            .table("students")
            .select("id, passport_versions(version_number, issued_at)")
            .eq("passport_id", passport_id)
            .limit(1)
            .execute()
        )
        rows = cast(list[dict[str, object]], response.data)
        if not rows:
            raise KeyError(passport_id)
        versions = cast(list[dict[str, object]], rows[0]["passport_versions"])
        newest = max(versions, key=lambda version: int(cast(int, version["version_number"])))
        issued_at = newest.get("issued_at")
        return LatestVersion(
            version=int(cast(int, newest["version_number"])),
            issued_on="1970-01-01" if issued_at is None else str(issued_at)[:10],
        )

    def versions_for_email(self, email: str) -> tuple[StoredVersion, ...]:
        response = (
            get_supabase()
            .table("students")
            .select(
                "email, full_name, passport_id, deleted_at, "
                "passport_versions(version_number, holder_name, verification_code, "
                "anchor_status, tx_hash, issued_at, pdf_en_path, pdf_ka_path, revoked_at, "
                "content_hash, anchored_at, "
                "skill_entries(skill, badge, awarded_on, description, position))"
            )
            .eq("email", email.strip().lower())
            .limit(1)
            .execute()
        )
        rows = cast(list[dict[str, object]], response.data)
        if not rows:
            return ()
        student = rows[0]
        nested = student.get("passport_versions")
        if not isinstance(nested, list):
            return ()
        versions: list[StoredVersion] = []
        for item in nested:
            if not isinstance(item, dict):
                continue
            row = cast(dict[str, object], dict(item))
            row["students"] = {
                "email": student.get("email"),
                "full_name": student.get("full_name"),
                "passport_id": student.get("passport_id"),
                "deleted_at": student.get("deleted_at"),
            }
            versions.append(_version_from_row(row))
        return tuple(versions)


def _anchor_status(value: str) -> AnchorStatus:
    return normalize_anchor_status(value)


def _version_from_row(row: dict[str, object]) -> StoredVersion:
    student = cast(dict[str, object], row["students"])
    skill_rows = cast(list[dict[str, object]], row["skill_entries"])
    ordered = sorted(skill_rows, key=lambda item: int(cast(int, item["position"])))
    skills = tuple(
        Skill(
            skill=str(item["skill"]),
            badge=str(item["badge"]),
            awarded_on=None if item["awarded_on"] is None else str(item["awarded_on"]),
            description=str(item.get("description") or ""),
        )
        for item in ordered
    )
    tx_hash = row["tx_hash"]
    issued_at = row.get("issued_at")
    pdf_en_path = row.get("pdf_en_path")
    pdf_ka_path = row.get("pdf_ka_path")
    revoked_at = row.get("revoked_at")
    archived_at = student.get("deleted_at")
    stored_hash = row.get("content_hash")
    anchored_at = row.get("anchored_at")
    return StoredVersion(
        passport_id=str(student["passport_id"]),
        email=str(student["email"]),
        full_name=str(student["full_name"]),
        version=int(cast(int, row["version_number"])),
        holder_name=str(row["holder_name"]),
        verification_code=str(row["verification_code"]),
        anchor_status=_anchor_status(str(row["anchor_status"])),
        tx_hash=None if tx_hash is None else str(tx_hash),
        issued_at="1970-01-01T00:00:00Z" if issued_at is None else str(issued_at),
        skills=skills,
        pdf_en_path=None if pdf_en_path is None else str(pdf_en_path),
        pdf_ka_path=None if pdf_ka_path is None else str(pdf_ka_path),
        version_revoked_at=None if revoked_at is None else str(revoked_at),
        student_archived_at=None if archived_at is None else str(archived_at),
        content_hash=None if stored_hash is None else str(stored_hash),
        anchored_at=None if anchored_at is None else str(anchored_at),
    )
