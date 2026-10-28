"""Admin API router.

All endpoints require a valid btu.edu.ge JWT whose email is in admin_users.
Sheet-managed students (admin_managed=False) are read-only from the admin
panel's perspective — their skills can only be changed via the Google Sheet.
"""

import re
import unicodedata
import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import Response
from postgrest import CountMethod

from passport_api.api.sync import get_sync_store
from passport_api.auth import require_admin
from passport_api.chain import chain_from_settings, publish_anchor
from passport_api.db import get_supabase
from passport_api.errors import APIError
from passport_api.fingerprint import (
    canonical_skills,
    content_hash,
    normalize_awarded_on,
    skill_fingerprint,
    verification_id_hash,
)
from passport_api.pdf import PassportPdf, get_storage, publish_pdfs
from passport_api.schemas import (
    AdminAwardRequest,
    AdminAwardResponse,
    AdminCatalogSkill,
    AdminCatalogSkillCreate,
    AdminCatalogSkillList,
    AdminCatalogSkillUpdate,
    AdminSkillAdd,
    AdminSkillEntry,
    AdminStudent,
    AdminStudentDetail,
    AdminStudentList,
    AdminSyncRun,
    AdminSyncRunList,
    AdminVersion,
    AdminVersionPending,
    AdminVersionPendingList,
    AwardRowResult,
    Skill,
    SyncResult,
)
from passport_api.settings import email_domain_allowed, settings
from passport_api.sheet_admin import (
    ALREADY_AWARDED,
    AdminGspreadSheet,
    AdminSheet,
    AwardInput,
)
from passport_api.sync import (
    CatalogSkill,
    GspreadSheet,
    RowOutcome,
    Sheet,
    SheetUnavailableError,
    SupabaseSyncStore,
    SyncStore,
    badge_for_category,
    run_sync,
)

router = APIRouter(prefix="/admin", tags=["admin"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _table_rows(data: object) -> list[dict[str, object]]:
    if not isinstance(data, list):
        return []
    return [cast(dict[str, object], row) for row in data if isinstance(row, dict)]


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())


def _skill_entry(row: dict[str, object], position: int) -> AdminSkillEntry:
    return AdminSkillEntry(
        id=cast(str, row["id"]),
        skill=str(row["skill"]),
        badge=str(row["badge"]),
        awarded_on=None if row.get("awarded_on") is None else str(row["awarded_on"]),
        description=str(row.get("description") or ""),
        position=position,
    )


def _version_from_row(row: dict[str, object]) -> AdminVersion:
    skill_rows = _table_rows(row.get("skill_entries"))
    ordered = sorted(skill_rows, key=lambda r: int(cast(int, r.get("position", 0))))
    skills = [_skill_entry(r, i + 1) for i, r in enumerate(ordered)]
    issued_raw = row.get("issued_at") or _now()
    return AdminVersion(
        id=cast(str, row["id"]),
        version_number=int(cast(int, row["version_number"])),
        holder_name=str(row["holder_name"]),
        verification_code=str(row["verification_code"]),
        anchor_status=cast(Literal["pending", "confirmed", "failed"], row["anchor_status"]),
        tx_hash=None if row.get("tx_hash") is None else str(row["tx_hash"]),
        issued_at=datetime.fromisoformat(str(issued_raw).replace("Z", "+00:00")),
        pdf_en_path=None if row.get("pdf_en_path") is None else str(row["pdf_en_path"]),
        pdf_ka_path=None if row.get("pdf_ka_path") is None else str(row["pdf_ka_path"]),
        skills=skills,
    )


def _student_row_to_summary(row: dict[str, object]) -> AdminStudent:
    versions = _table_rows(row.get("passport_versions"))
    version_count = len(versions)
    latest_anchor: str | None = None
    if versions:
        latest_v = max(versions, key=lambda v: int(cast(int, v["version_number"])))
        latest_anchor = str(latest_v["anchor_status"])
    deleted_raw = row.get("deleted_at")
    created_raw = row.get("created_at") or _now()
    return AdminStudent(
        id=cast(str, row["id"]),
        email=str(row["email"]),
        full_name=str(row["full_name"]),
        passport_id=str(row["passport_id"]),
        admin_managed=bool(row.get("admin_managed", False)),
        deleted_at=(
            None
            if deleted_raw is None
            else datetime.fromisoformat(str(deleted_raw).replace("Z", "+00:00"))
        ),
        version_count=version_count,
        latest_anchor_status=cast(Literal["pending", "confirmed", "failed"] | None, latest_anchor),
        created_at=datetime.fromisoformat(str(created_raw).replace("Z", "+00:00")),
    )


def _require_admin_student(passport_id: str) -> dict[str, object]:
    """Return a student row; raise 404 if not found."""
    try:
        response = (
            get_supabase()
            .table("students")
            .select("id, email, full_name, passport_id, admin_managed, deleted_at, created_at")
            .eq("passport_id", passport_id)
            .limit(1)
            .execute()
        )
        rows = _table_rows(response.data)
        if not rows:
            raise APIError(404, "student_not_found")
        return rows[0]
    except RuntimeError as exc:
        if "supabase_not_configured" in str(exc):
            s = _demo_store.students.get(passport_id)
            if s is None:
                raise APIError(404, "student_not_found") from exc
            return s
        raise


def _latest_skills_for_student(student_id: str) -> tuple[list[dict[str, object]], int]:
    """Return (skill_entry rows, latest_version_number) or ([], 0) for a new student."""
    response = (
        get_supabase()
        .table("passport_versions")
        .select(
            "id, version_number, skill_entries(id, skill, badge, awarded_on, description, position)"
        )
        .eq("student_id", student_id)
        .order("version_number", desc=True)
        .limit(1)
        .execute()
    )
    rows = _table_rows(response.data)
    if not rows:
        return [], 0
    skill_rows = _table_rows(rows[0].get("skill_entries"))
    return skill_rows, int(cast(int, rows[0]["version_number"]))


def _issue_new_version_for_admin(
    student_row: dict[str, object],
    new_skills: tuple[Skill, ...],
    next_version_number: int,
) -> None:
    """Create a new passport version, PDFs, and initiate anchoring."""
    email = str(student_row["email"])
    passport_id = str(student_row["passport_id"])
    holder_name = str(student_row["full_name"])
    fingerprint = skill_fingerprint(new_skills)
    document_hash = content_hash(
        holder_name=holder_name,
        passport_id=passport_id,
        skills=new_skills,
        version=next_version_number,
    )

    # Reuse sync helpers for code/hash minting
    supabase = get_supabase()
    codes_resp = supabase.table("passport_versions").select("verification_code").execute()
    codes: set[str] = {str(r["verification_code"]) for r in _table_rows(codes_resp.data)}
    hashes_resp = supabase.table("passport_versions").select("content_hash").execute()
    content_hashes: set[str] = {str(r["content_hash"]) for r in _table_rows(hashes_resp.data)}

    from passport_api.sync import _format_code, _mint  # noqa: PLC0415

    code = _mint(codes, 16, _format_code)
    vid_hash = verification_id_hash(code)

    if document_hash in content_hashes:
        raise RuntimeError("content_hash_collision")

    # Insert version row
    version_resp = (
        supabase.table("passport_versions")
        .insert(
            {
                "student_id": str(student_row["id"]),
                "version_number": next_version_number,
                "holder_name": holder_name,
                "verification_code": code,
                "verification_id_hash": vid_hash,
                "skill_fingerprint": fingerprint,
                "content_hash": document_hash,
                "anchor_status": "pending",
                "issued_at": _now(),
            }
        )
        .execute()
    )
    version_rows = _table_rows(version_resp.data)
    if not version_rows:
        raise RuntimeError("version_not_created")
    version_id = str(version_rows[0]["id"])

    # Insert skill entries
    skill_rows = [
        {
            "version_id": version_id,
            "skill": s.skill,
            "badge": s.badge,
            "awarded_on": s.awarded_on,
            "description": s.description,
            "position": pos,
        }
        for pos, s in enumerate(new_skills, start=1)
    ]
    if skill_rows:
        supabase.table("skill_entries").insert(skill_rows).execute()

    # Generate PDFs
    storage = get_storage()
    en_path, ka_path = publish_pdfs(
        PassportPdf(
            holder_name=holder_name,
            passport_id=passport_id,
            version=next_version_number,
            issued_on=_now()[:10],
            verification_code=code,
            skills=new_skills,
        ),
        storage,
    )
    supabase.table("passport_versions").update({"pdf_en_path": en_path, "pdf_ka_path": ka_path}).eq(
        "id", version_id
    ).execute()

    # Anchor
    chain = chain_from_settings()
    if chain is not None:
        from passport_api.sync import VersionRecord  # noqa: PLC0415

        vr = VersionRecord(
            passport_id=passport_id,
            email=email,
            version_number=next_version_number,
            holder_name=holder_name,
            verification_code=code,
            verification_id_hash=vid_hash,
            skill_fingerprint=fingerprint,
            content_hash=document_hash,
            anchor_status="pending",
            pdf_en_path=en_path,
            pdf_ka_path=ka_path,
            tx_hash=None,
            issued_at=_now(),
            skills=new_skills,
        )
        try:
            publish_anchor(vr, chain, now=_now())
        except Exception:
            vr.anchor_status = "failed"
        supabase.table("passport_versions").update(
            {
                "anchor_status": vr.anchor_status,
                "tx_hash": vr.tx_hash,
                "anchored_at": vr.anchored_at,
            }
        ).eq("id", version_id).execute()


class _DemoStore:
    def __init__(self) -> None:
        self.students: dict[str, dict[str, Any]] = {
            "BTU-A1B2C3D4E5": {
                "id": uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001"),
                "email": "demo.student@btu.edu.ge",
                "full_name": "Nino Beridze",
                "passport_id": "BTU-A1B2C3D4E5",
                "admin_managed": False,
                "deleted_at": None,
                "created_at": datetime.fromisoformat("2025-01-15T00:00:00+00:00"),
                "versions": [
                    AdminVersion(
                        id=uuid.UUID("11111111-0002-0000-0000-000000000001"),
                        version_number=2,
                        holder_name="Nino Beridze",
                        verification_code="A1B2-C3D4-E5F6-G7H8",
                        anchor_status="confirmed",
                        tx_hash="0x" + "11" * 32,
                        issued_at=datetime.fromisoformat("2025-06-01T00:00:00+00:00"),
                        pdf_en_path="BTU-A1B2C3D4E5/v2/en.pdf",
                        pdf_ka_path="BTU-A1B2C3D4E5/v2/ka.pdf",
                        skills=[
                            AdminSkillEntry(
                                id=uuid.UUID("eeeeeeee-0002-0000-0000-000000000001"),
                                skill="Machine Learning",
                                badge="Stamp",
                                awarded_on="2025-06-01",
                                description="Applied machine learning models and pipelines.",
                                position=1,
                            )
                        ],
                    ),
                    AdminVersion(
                        id=uuid.UUID("11111111-0001-0000-0000-000000000001"),
                        version_number=1,
                        holder_name="Nino Beridze",
                        verification_code="K9M2-N3P4-Q5R6-S7T8",
                        anchor_status="confirmed",
                        tx_hash="0x" + "22" * 32,
                        issued_at=datetime.fromisoformat("2025-01-15T00:00:00+00:00"),
                        pdf_en_path="BTU-A1B2C3D4E5/v1/en.pdf",
                        pdf_ka_path="BTU-A1B2C3D4E5/v1/ka.pdf",
                        skills=[
                            AdminSkillEntry(
                                id=uuid.UUID("eeeeeeee-0001-0000-0000-000000000001"),
                                skill="Python",
                                badge="Foundation",
                                awarded_on="2025-01-15",
                                description="Python language basics and data structures.",
                                position=1,
                            )
                        ],
                    ),
                ],
            },
            "BTU-V2W3X4Y5Z6": {
                "id": uuid.UUID("aaaaaaaa-0000-0000-0000-000000000002"),
                "email": "error.student@btu.edu.ge",
                "full_name": "Giorgi Kapanadze",
                "passport_id": "BTU-V2W3X4Y5Z6",
                "admin_managed": True,
                "deleted_at": None,
                "created_at": datetime.fromisoformat("2025-03-01T00:00:00+00:00"),
                "versions": [
                    AdminVersion(
                        id=uuid.UUID("11111111-0003-0000-0000-000000000001"),
                        version_number=1,
                        holder_name="Giorgi Kapanadze",
                        verification_code="V2W3-X4Y5-Z6A7-B8C9",
                        anchor_status="pending",
                        tx_hash=None,
                        issued_at=datetime.fromisoformat("2025-03-01T00:00:00+00:00"),
                        pdf_en_path=None,
                        pdf_ka_path=None,
                        skills=[
                            AdminSkillEntry(
                                id=uuid.UUID("eeeeeeee-0003-0000-0000-000000000001"),
                                skill="Prompting",
                                badge="Badge",
                                awarded_on=None,
                                description="Advanced system prompting and context engineering.",
                                position=1,
                            )
                        ],
                    ),
                ],
            },
        }
        self.sync_runs: list[AdminSyncRun] = [
            AdminSyncRun(
                id=uuid.UUID("99999999-0001-0000-0000-000000000001"),
                status="completed",
                started_at=datetime.fromisoformat("2026-10-28T14:15:00+00:00"),
                finished_at=datetime.fromisoformat("2026-10-28T14:15:04+00:00"),
                rows_read=54,
                versions_created=2,
                error=None,
            ),
            AdminSyncRun(
                id=uuid.UUID("99999999-0002-0000-0000-000000000002"),
                status="skipped",
                started_at=datetime.fromisoformat("2026-10-28T14:00:00+00:00"),
                finished_at=datetime.fromisoformat("2026-10-28T14:00:01+00:00"),
                rows_read=0,
                versions_created=0,
                error=None,
            ),
        ]

    def list_students(
        self, search: str | None, include_deleted: bool, offset: int, limit: int
    ) -> AdminStudentList:
        filtered = list(self.students.values())
        if not include_deleted:
            filtered = [s for s in filtered if s["deleted_at"] is None]
        if search:
            q = search.lower()
            filtered = [
                s
                for s in filtered
                if q in str(s["email"]).lower() or q in str(s["full_name"]).lower()
            ]
        total = len(filtered)
        paged = filtered[offset : offset + limit]
        summaries = [
            AdminStudent(
                id=s["id"],
                email=s["email"],
                full_name=s["full_name"],
                passport_id=s["passport_id"],
                admin_managed=s["admin_managed"],
                deleted_at=s["deleted_at"],
                version_count=len(s["versions"]),
                latest_anchor_status=s["versions"][0].anchor_status if s["versions"] else None,
                created_at=s["created_at"],
            )
            for s in paged
        ]
        return AdminStudentList(students=summaries, total=total)

    def get_student(self, passport_id: str) -> AdminStudentDetail:
        s = self.students.get(passport_id)
        if s is None:
            raise APIError(404, "student_not_found")
        return AdminStudentDetail(
            id=s["id"],
            email=s["email"],
            full_name=s["full_name"],
            passport_id=s["passport_id"],
            admin_managed=s["admin_managed"],
            deleted_at=s["deleted_at"],
            created_at=s["created_at"],
            versions=s["versions"],
        )

    def delete_student(self, passport_id: str) -> None:
        s = self.students.get(passport_id)
        if s is None:
            raise APIError(404, "student_not_found")
        if s["deleted_at"] is not None:
            raise APIError(409, "student_already_deleted")
        s["deleted_at"] = datetime.now(UTC)

    def add_skill(self, passport_id: str, body: AdminSkillAdd) -> AdminStudentDetail:
        s = self.students.get(passport_id)
        if s is None:
            raise APIError(404, "student_not_found")
        if not s["admin_managed"]:
            raise APIError(422, "sheet_managed_student")
        if s["deleted_at"] is not None:
            raise APIError(409, "student_already_deleted")
        latest_v = s["versions"][0] if s["versions"] else None
        current_skills = list(latest_v.skills) if latest_v else []
        new_v_num = (latest_v.version_number + 1) if latest_v else 1
        new_skill = AdminSkillEntry(
            id=uuid.uuid4(),
            skill=body.skill.strip(),
            badge=body.badge.strip(),
            awarded_on=body.awarded_on.isoformat() if body.awarded_on else None,
            description="",
            position=len(current_skills) + 1,
        )
        import secrets

        raw_code = "".join(secrets.choice("0123456789ABCDEFGHJKMNPQRSTVWXYZ") for _ in range(16))
        code = f"{raw_code[0:4]}-{raw_code[4:8]}-{raw_code[8:12]}-{raw_code[12:16]}"
        v = AdminVersion(
            id=uuid.uuid4(),
            version_number=new_v_num,
            holder_name=s["full_name"],
            verification_code=code,
            anchor_status="confirmed",
            tx_hash="0x" + "aa" * 32,
            issued_at=datetime.now(UTC),
            pdf_en_path=f"{passport_id}/v{new_v_num}/en.pdf",
            pdf_ka_path=f"{passport_id}/v{new_v_num}/ka.pdf",
            skills=[new_skill] + current_skills,
        )
        s["versions"].insert(0, v)
        return self.get_student(passport_id)

    def remove_skill(self, passport_id: str, skill_id: str) -> AdminStudentDetail:
        s = self.students.get(passport_id)
        if s is None:
            raise APIError(404, "student_not_found")
        if not s["admin_managed"]:
            raise APIError(422, "sheet_managed_student")
        if s["deleted_at"] is not None:
            raise APIError(409, "student_already_deleted")
        latest_v = s["versions"][0] if s["versions"] else None
        if not latest_v:
            raise APIError(404, "skill_not_found")
        target_uuid = (
            uuid.UUID(skill_id) if isinstance(skill_id, str) and len(skill_id) == 36 else None
        )
        remaining = [
            sk for sk in latest_v.skills if sk.id != target_uuid and str(sk.id) != skill_id
        ]
        if len(remaining) == len(latest_v.skills):
            raise APIError(404, "skill_not_found")
        new_v_num = latest_v.version_number + 1
        import secrets

        raw_code = "".join(secrets.choice("0123456789ABCDEFGHJKMNPQRSTVWXYZ") for _ in range(16))
        code = f"{raw_code[0:4]}-{raw_code[4:8]}-{raw_code[8:12]}-{raw_code[12:16]}"
        v = AdminVersion(
            id=uuid.uuid4(),
            version_number=new_v_num,
            holder_name=s["full_name"],
            verification_code=code,
            anchor_status="confirmed",
            tx_hash="0x" + "bb" * 32,
            issued_at=datetime.now(UTC),
            pdf_en_path=f"{passport_id}/v{new_v_num}/en.pdf",
            pdf_ka_path=f"{passport_id}/v{new_v_num}/ka.pdf",
            skills=remaining,
        )
        s["versions"].insert(0, v)
        return self.get_student(passport_id)

    def list_sync_runs(self, limit: int) -> AdminSyncRunList:
        return AdminSyncRunList(runs=self.sync_runs[:limit])

    def trigger_sync(self) -> SyncResult:
        run = AdminSyncRun(
            id=uuid.uuid4(),
            status="completed",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            rows_read=54,
            versions_created=1,
            error=None,
        )
        self.sync_runs.insert(0, run)
        return SyncResult(status="completed", rows_read=54, versions_created=1, error=None)

    def list_pending_versions(self) -> AdminVersionPendingList:
        pending = []
        for s in self.students.values():
            for v in s["versions"]:
                if v.anchor_status in ("pending", "failed"):
                    pending.append(
                        AdminVersionPending(
                            version_id=v.id,
                            passport_id=s["passport_id"],
                            holder_name=s["full_name"],
                            version_number=v.version_number,
                            anchor_status=cast(Literal["pending", "failed"], v.anchor_status),
                            issued_at=v.issued_at,
                            tx_hash=v.tx_hash,
                        )
                    )
        return AdminVersionPendingList(versions=pending)

    def retry_anchor(self, version_id: str) -> dict[str, str]:
        vid = uuid.UUID(version_id) if len(version_id) == 36 else None
        for s in self.students.values():
            for v in s["versions"]:
                if v.id == vid or str(v.id) == version_id:
                    if v.anchor_status == "confirmed":
                        raise APIError(409, "anchor_already_confirmed")
                    v.anchor_status = "confirmed"
                    v.tx_hash = "0x" + "33" * 32
                    return {"status": "confirmed"}
        raise APIError(404, "version_not_found")


_demo_store = _DemoStore()


# ---------------------------------------------------------------------------
# Students — read
# ---------------------------------------------------------------------------


@router.get("/students", response_model=AdminStudentList)
def list_students(
    authorization: Annotated[str | None, Header()] = None,
    search: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> AdminStudentList:
    require_admin(authorization)
    try:
        query = (
            get_supabase()
            .table("students")
            .select(
                "id, email, full_name, passport_id, admin_managed, deleted_at, created_at, "
                "passport_versions(version_number, anchor_status)"
            )
        )
        if not include_deleted:
            query = query.is_("deleted_at", "null")
        if search:
            like = f"%{search}%"
            query = query.or_(f"email.ilike.{like},full_name.ilike.{like}")
        count_resp = (
            get_supabase()
            .table("students")
            .select("id", count=CountMethod.exact)
            .is_("deleted_at", "null" if not include_deleted else None)
            .execute()
        )
        total = count_resp.count or 0
        rows_resp = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        students = [_student_row_to_summary(r) for r in _table_rows(rows_resp.data)]
        return AdminStudentList(students=students, total=total)
    except RuntimeError as exc:
        if "supabase_not_configured" in str(exc):
            return _demo_store.list_students(search, include_deleted, offset, limit)
        raise


@router.get("/students/{passport_id}", response_model=AdminStudentDetail)
def get_student(
    passport_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> AdminStudentDetail:
    require_admin(authorization)
    try:
        student = _require_admin_student(passport_id)
        versions_resp = (
            get_supabase()
            .table("passport_versions")
            .select(
                "id, version_number, holder_name, verification_code, anchor_status, "
                "tx_hash, issued_at, pdf_en_path, pdf_ka_path, "
                "skill_entries(id, skill, badge, awarded_on, description, position)"
            )
            .eq("student_id", str(student["id"]))
            .order("version_number", desc=True)
            .execute()
        )
        versions = [_version_from_row(r) for r in _table_rows(versions_resp.data)]
        deleted_raw = student.get("deleted_at")
        created_raw = student.get("created_at") or _now()
        return AdminStudentDetail(
            id=cast(str, student["id"]),
            email=str(student["email"]),
            full_name=str(student["full_name"]),
            passport_id=str(student["passport_id"]),
            admin_managed=bool(student.get("admin_managed", False)),
            deleted_at=(
                None
                if deleted_raw is None
                else datetime.fromisoformat(str(deleted_raw).replace("Z", "+00:00"))
            ),
            created_at=datetime.fromisoformat(str(created_raw).replace("Z", "+00:00")),
            versions=versions,
        )
    except RuntimeError as exc:
        if "supabase_not_configured" in str(exc):
            return _demo_store.get_student(passport_id)
        raise


# ---------------------------------------------------------------------------
# Students — write (new students are created by awarding a skill, see /admin/awards)
# ---------------------------------------------------------------------------


@router.delete("/students/{passport_id}", status_code=204)
def delete_student(
    passport_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    require_admin(authorization)
    try:
        student = _require_admin_student(passport_id)
        if student.get("deleted_at") is not None:
            raise APIError(409, "student_already_deleted")
        get_supabase().table("students").update({"deleted_at": _now()}).eq(
            "id", str(student["id"])
        ).execute()
        return Response(status_code=204)
    except RuntimeError as exc:
        if "supabase_not_configured" in str(exc):
            _demo_store.delete_student(passport_id)
            return Response(status_code=204)
        raise


# ---------------------------------------------------------------------------
# Skills — write (admin_managed students only)
# ---------------------------------------------------------------------------


@router.post("/students/{passport_id}/skills", response_model=AdminStudentDetail, status_code=201)
def add_skill(
    passport_id: str,
    body: AdminSkillAdd,
    authorization: Annotated[str | None, Header()] = None,
) -> AdminStudentDetail:
    require_admin(authorization)
    try:
        student = _require_admin_student(passport_id)

        if not student.get("admin_managed"):
            raise APIError(422, "sheet_managed_student")
        if student.get("deleted_at") is not None:
            raise APIError(409, "student_already_deleted")

        current_skill_rows, latest_version = _latest_skills_for_student(str(student["id"]))

        # Build new skill list: existing + new entry
        existing_skills = [
            Skill(
                skill=str(r["skill"]),
                badge=str(r["badge"]),
                awarded_on=None if r.get("awarded_on") is None else str(r["awarded_on"]),
                description=str(r.get("description") or ""),
            )
            for r in current_skill_rows
        ]
        awarded_str = body.awarded_on.isoformat() if body.awarded_on else None
        new_entry = Skill(
            skill=_nfc(body.skill),
            badge=_nfc(body.badge),
            awarded_on=normalize_awarded_on(awarded_str or ""),
            description="",
        )
        all_skills = tuple(canonical_skills(existing_skills + [new_entry]))
        _issue_new_version_for_admin(student, all_skills, latest_version + 1)
        return get_student(passport_id, authorization)
    except RuntimeError as exc:
        if "supabase_not_configured" in str(exc):
            return _demo_store.add_skill(passport_id, body)
        raise


@router.delete(
    "/students/{passport_id}/skills/{skill_id}",
    response_model=AdminStudentDetail,
)
def remove_skill(
    passport_id: str,
    skill_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> AdminStudentDetail:
    require_admin(authorization)
    try:
        student = _require_admin_student(passport_id)

        if not student.get("admin_managed"):
            raise APIError(422, "sheet_managed_student")
        if student.get("deleted_at") is not None:
            raise APIError(409, "student_already_deleted")

        current_skill_rows, latest_version = _latest_skills_for_student(str(student["id"]))

        # Find and remove the target skill
        remaining_rows = [r for r in current_skill_rows if str(r["id"]) != skill_id]
        if len(remaining_rows) == len(current_skill_rows):
            raise APIError(404, "skill_not_found")

        remaining_skills = tuple(
            canonical_skills(
                [
                    Skill(
                        skill=str(r["skill"]),
                        badge=str(r["badge"]),
                        awarded_on=None if r.get("awarded_on") is None else str(r["awarded_on"]),
                        description=str(r.get("description") or ""),
                    )
                    for r in remaining_rows
                ]
            )
        )
        _issue_new_version_for_admin(student, remaining_skills, latest_version + 1)
        return get_student(passport_id, authorization)
    except RuntimeError as exc:
        if "supabase_not_configured" in str(exc):
            return _demo_store.remove_skill(passport_id, skill_id)
        raise


# ---------------------------------------------------------------------------
# Sync operations
# ---------------------------------------------------------------------------


@router.get("/sync-runs", response_model=AdminSyncRunList)
def list_sync_runs(
    authorization: Annotated[str | None, Header()] = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> AdminSyncRunList:
    require_admin(authorization)
    try:
        resp = (
            get_supabase()
            .table("sync_runs")
            .select("id, status, started_at, finished_at, rows_read, versions_created, error")
            .order("started_at", desc=True)
            .limit(limit)
            .execute()
        )
        runs: list[AdminSyncRun] = []
        for r in _table_rows(resp.data):
            started_raw = r.get("started_at") or _now()
            finished_raw = r.get("finished_at")
            runs.append(
                AdminSyncRun(
                    id=cast(str, r["id"]),
                    status=cast(Literal["running", "completed", "skipped", "failed"], r["status"]),
                    started_at=datetime.fromisoformat(str(started_raw).replace("Z", "+00:00")),
                    finished_at=(
                        None
                        if finished_raw is None
                        else datetime.fromisoformat(str(finished_raw).replace("Z", "+00:00"))
                    ),
                    rows_read=(
                        None if r.get("rows_read") is None else int(cast(int, r["rows_read"]))
                    ),
                    versions_created=(
                        None
                        if r.get("versions_created") is None
                        else int(cast(int, r["versions_created"]))
                    ),
                    error=None if r.get("error") is None else str(r["error"]),
                )
            )
        return AdminSyncRunList(runs=runs)
    except RuntimeError as exc:
        if "supabase_not_configured" in str(exc):
            return _demo_store.list_sync_runs(limit)
        raise


@router.post("/sync", response_model=SyncResult)
def trigger_sync(
    authorization: Annotated[str | None, Header()] = None,
) -> SyncResult:
    require_admin(authorization)
    if not (settings.supabase_url and settings.supabase_service_role_key):
        return _demo_store.trigger_sync()
    return run_sync(SupabaseSyncStore(), GspreadSheet())


# ---------------------------------------------------------------------------
# Skills catalog (Skills tab first, then the skills table)
# ---------------------------------------------------------------------------

_SKILL_COLUMNS = "id, name, name_ka, category, badge, description"
_SKILL_ID = re.compile(r"^SKL-(\d+)$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def get_admin_sheet() -> AdminSheet:
    return AdminGspreadSheet()


_admin_sheet_dependency = Depends(get_admin_sheet)
_sync_store_dependency = Depends(get_sync_store)


@contextmanager
def _sheet_errors() -> Iterator[None]:
    try:
        yield
    except SheetUnavailableError as exc:
        raise APIError(503, "sheet_unavailable") from exc


def _skills_table() -> Any:
    try:
        return get_supabase().table("skills")
    except RuntimeError as exc:
        if "supabase_not_configured" in str(exc):
            raise APIError(503, "sheet_unavailable") from exc
        raise


def _catalog_row(row: dict[str, object]) -> AdminCatalogSkill:
    return AdminCatalogSkill(
        id=str(row["id"]),
        name=str(row["name"]),
        name_ka=str(row.get("name_ka") or ""),
        category=str(row.get("category") or ""),
        badge=str(row.get("badge") or ""),
        description=str(row.get("description") or ""),
    )


def _db_skills() -> list[AdminCatalogSkill]:
    response = _skills_table().select(_SKILL_COLUMNS).order("id").execute()
    return [_catalog_row(row) for row in _table_rows(response.data)]


def _as_catalog(skill: AdminCatalogSkill) -> CatalogSkill:
    return CatalogSkill(
        id=skill.id,
        name=skill.name,
        category=skill.category,
        badge=skill.badge,
        description=skill.description,
        name_ka=skill.name_ka,
    )


def _as_admin_skill(skill: CatalogSkill) -> AdminCatalogSkill:
    return AdminCatalogSkill(
        id=skill.id,
        name=skill.name,
        name_ka=skill.name_ka or "",
        category=skill.category,
        badge=skill.badge,
        description=skill.description,
    )


def _upsert_skill(skill: CatalogSkill) -> None:
    _skills_table().upsert(
        {
            "id": skill.id,
            "name": skill.name,
            "name_ka": skill.name_ka or "",
            "category": skill.category,
            "badge": skill.badge,
            "description": skill.description,
            "updated_at": _now(),
        },
        on_conflict="id",
    ).execute()


def _name_key(name: str) -> str:
    return _nfc(name).casefold()


def _next_skill_id(ids: Iterable[str]) -> str:
    numbers = [int(match.group(1)) for i in ids if (match := _SKILL_ID.match(i.upper()))]
    return f"SKL-{max(numbers, default=0) + 1:03d}"


@router.get("/skills", response_model=AdminCatalogSkillList)
def list_skills(
    authorization: Annotated[str | None, Header()] = None,
) -> AdminCatalogSkillList:
    require_admin(authorization)
    return AdminCatalogSkillList(skills=_db_skills())


@router.post("/skills", response_model=AdminCatalogSkill, status_code=201)
def create_skill(
    body: AdminCatalogSkillCreate,
    authorization: Annotated[str | None, Header()] = None,
    sheet: AdminSheet = _admin_sheet_dependency,
) -> AdminCatalogSkill:
    require_admin(authorization)
    name = _nfc(body.name)
    key = _name_key(name)
    db_skills = _db_skills()
    if any(_name_key(skill.name) == key for skill in db_skills):
        raise APIError(409, "skill_name_taken")
    with _sheet_errors():
        tab = sheet.ensure_skills_tab([_as_catalog(skill) for skill in db_skills])
    # A skill already in the tab but missing from the database means an earlier save
    # stopped halfway. Finish it instead of creating a second row.
    unfinished = next((skill for skill in tab if _name_key(skill.name) == key), None)
    if unfinished is not None:
        _upsert_skill(unfinished)
        return _as_admin_skill(unfinished)
    skill = CatalogSkill(
        id=_next_skill_id([*(s.id for s in db_skills), *(s.id for s in tab)]),
        name=name,
        category=body.category,
        badge=badge_for_category(body.category),
        description=_nfc(body.description),
        name_ka=_nfc(body.name_ka),
    )
    with _sheet_errors():
        sheet.append_skill(skill)
    _upsert_skill(skill)
    return _as_admin_skill(skill)


@router.patch("/skills/{skill_id}", response_model=AdminCatalogSkill)
def update_skill(
    skill_id: str,
    body: AdminCatalogSkillUpdate,
    authorization: Annotated[str | None, Header()] = None,
    sheet: AdminSheet = _admin_sheet_dependency,
) -> AdminCatalogSkill:
    require_admin(authorization)
    skill_id = skill_id.strip().upper()
    db_skills = _db_skills()
    with _sheet_errors():
        tab = sheet.ensure_skills_tab([_as_catalog(skill) for skill in db_skills])
    current = next((skill for skill in tab if skill.id == skill_id), None)
    if current is None:
        stored = next((skill for skill in db_skills if skill.id == skill_id), None)
        current = None if stored is None else _as_catalog(stored)
    if current is None:
        raise APIError(404, "skill_not_found")
    name = current.name if body.name is None else _nfc(body.name)
    category = current.category if body.category is None else body.category
    merged = CatalogSkill(
        id=skill_id,
        name=name,
        category=category,
        badge=badge_for_category(category),
        description=current.description if body.description is None else _nfc(body.description),
        name_ka=(current.name_ka or "") if body.name_ka is None else _nfc(body.name_ka),
    )
    key = _name_key(name)
    others = [*db_skills, *(_as_admin_skill(skill) for skill in tab)]
    if any(other.id != skill_id and _name_key(other.name) == key for other in others):
        raise APIError(409, "skill_name_taken")
    with _sheet_errors():
        if not sheet.update_skill(merged):
            sheet.append_skill(merged)
    _upsert_skill(merged)
    return _as_admin_skill(merged)


# ---------------------------------------------------------------------------
# Awards: rows go to the Sheet, then the sync copies them into the database
# ---------------------------------------------------------------------------


class _RecordingSheet:
    """Passes everything to the real sheet and remembers the per-row sync outcomes."""

    def __init__(self, inner: Sheet) -> None:
        self._inner = inner
        self.outcomes: dict[int, RowOutcome] = {}

    def read_rows(self) -> list[dict[str, object]]:
        return self._inner.read_rows()

    def read_catalog(self) -> list[CatalogSkill]:
        reader = getattr(self._inner, "read_catalog", None)
        return cast(list[CatalogSkill], reader()) if callable(reader) else []

    def write_back(self, outcomes: list[RowOutcome]) -> None:
        self.outcomes.update({outcome.index: outcome for outcome in outcomes})
        self._inner.write_back(outcomes)


@router.post("/awards", response_model=AdminAwardResponse)
def award_skill(
    body: AdminAwardRequest,
    authorization: Annotated[str | None, Header()] = None,
    sheet: AdminSheet = _admin_sheet_dependency,
    store: SyncStore = _sync_store_dependency,
) -> AdminAwardResponse:
    require_admin(authorization)
    response = (
        _skills_table().select(_SKILL_COLUMNS).eq("id", body.skill_id.strip().upper()).execute()
    )
    rows = _table_rows(response.data)
    if not rows:
        raise APIError(404, "skill_not_found")
    skill = _catalog_row(rows[0])
    level = body.level or skill.category
    badge = badge_for_category(level)
    if not badge:
        raise APIError(422, "award_level_required")
    awarded_on = (body.awarded_on or datetime.now(UTC).date()).isoformat()

    order: list[str] = []
    results: dict[str, AwardRowResult] = {}
    awards: list[AwardInput] = []
    for student in body.students:
        email = _nfc(student.email).lower()
        if email in results or any(a.email == email for a in awards):
            continue
        order.append(email)
        if not _EMAIL.match(email):
            results[email] = AwardRowResult(email=email, status="failed", error="invalid_email")
        elif not email_domain_allowed(email):
            results[email] = AwardRowResult(
                email=email, status="failed", error="email_domain_not_allowed"
            )
        else:
            awards.append(
                AwardInput(
                    email=email,
                    first_name=_nfc(student.first_name),
                    last_name=_nfc(student.last_name),
                    skill_id=skill.id,
                    skill_name=skill.name,
                    category=level,
                    badge=badge,
                    description=skill.description,
                    awarded_on=awarded_on,
                )
            )

    placed: dict[str, int] = {}
    if awards:
        with _sheet_errors():
            placements = sheet.append_awards(awards, set(store.current_students()))
        for placement in placements:
            if placement.row_number is not None:
                placed[placement.email] = placement.row_number
            else:
                results[placement.email] = AwardRowResult(
                    email=placement.email,
                    status="skipped" if placement.error == ALREADY_AWARDED else "failed",
                    error=placement.error,
                )

    sync_result = SyncResult(status="skipped", rows_read=0, versions_created=0, error=None)
    if placed:
        recorder = _RecordingSheet(sheet)
        try:
            sync_result = run_sync(store, recorder)
        except Exception:
            sync_result = SyncResult(
                status="failed", rows_read=0, versions_created=0, error="sync_failed"
            )
        for email, row_number in placed.items():
            outcome = recorder.outcomes.get(sheet.data_index(row_number))
            if outcome is None:
                # Not synced yet (another sync was running, or it failed). The rows are in
                # the sheet, so the next scheduled sync picks them up.
                results[email] = AwardRowResult(email=email, status="pending")
            elif outcome.status == "SYNCED":
                results[email] = AwardRowResult(
                    email=email,
                    status="synced",
                    passport_id=outcome.passport_id,
                    version=outcome.version,
                )
            else:
                results[email] = AwardRowResult(
                    email=email,
                    status="failed",
                    error=outcome.error,
                    passport_id=outcome.passport_id,
                )
    return AdminAwardResponse(rows=[results[email] for email in order], sync_result=sync_result)


# ---------------------------------------------------------------------------
# Anchor operations
# ---------------------------------------------------------------------------


@router.get("/versions/pending", response_model=AdminVersionPendingList)
def list_pending_versions(
    authorization: Annotated[str | None, Header()] = None,
) -> AdminVersionPendingList:
    require_admin(authorization)
    try:
        resp = (
            get_supabase()
            .table("passport_versions")
            .select(
                "id, version_number, holder_name, anchor_status, tx_hash, issued_at, "
                "students(passport_id)"
            )
            .in_("anchor_status", ["pending", "failed"])
            .order("issued_at", desc=True)
            .execute()
        )
        versions: list[AdminVersionPending] = []
        for r in _table_rows(resp.data):
            student_embed = r.get("students")
            if isinstance(student_embed, list):
                student_embed = student_embed[0] if student_embed else None
            passport_id = (
                str(cast(dict[str, object], student_embed)["passport_id"]) if student_embed else ""
            )
            issued_raw = r.get("issued_at") or _now()
            versions.append(
                AdminVersionPending(
                    version_id=cast(str, r["id"]),
                    passport_id=passport_id,
                    holder_name=str(r["holder_name"]),
                    version_number=int(cast(int, r["version_number"])),
                    anchor_status=cast(Literal["pending", "failed"], r["anchor_status"]),
                    issued_at=datetime.fromisoformat(str(issued_raw).replace("Z", "+00:00")),
                    tx_hash=None if r.get("tx_hash") is None else str(r["tx_hash"]),
                )
            )
        return AdminVersionPendingList(versions=versions)
    except RuntimeError as exc:
        if "supabase_not_configured" in str(exc):
            return _demo_store.list_pending_versions()
        raise


@router.post("/versions/{version_id}/anchor", status_code=200)
def retry_anchor(
    version_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    require_admin(authorization)
    try:
        resp = (
            get_supabase()
            .table("passport_versions")
            .select(
                "id, version_number, holder_name, verification_code, verification_id_hash, "
                "skill_fingerprint, content_hash, anchor_status, tx_hash, anchored_at, issued_at, "
                "skill_entries(skill, badge, awarded_on, description, position), "
                "students(email, passport_id)"
            )
            .eq("id", version_id)
            .limit(1)
            .execute()
        )
        rows = _table_rows(resp.data)
        if not rows:
            raise APIError(404, "version_not_found")
        row = rows[0]
        if str(row["anchor_status"]) == "confirmed":
            raise APIError(409, "anchor_already_confirmed")

        student_embed = row.get("students")
        if isinstance(student_embed, list):
            student_embed = student_embed[0] if student_embed else None
        if not isinstance(student_embed, dict):
            raise RuntimeError("student_missing")
        student = cast(dict[str, object], student_embed)

        skill_rows = sorted(
            _table_rows(row.get("skill_entries")),
            key=lambda r: int(cast(int, r.get("position", 0))),
        )
        skills = tuple(
            Skill(
                skill=str(r["skill"]),
                badge=str(r["badge"]),
                awarded_on=None if r.get("awarded_on") is None else str(r["awarded_on"]),
                description=str(r.get("description") or ""),
            )
            for r in skill_rows
        )

        from passport_api.sync import VersionRecord  # noqa: PLC0415

        issued_raw = row.get("issued_at") or _now()
        tx_hash = row.get("tx_hash")
        anchored_at = row.get("anchored_at")
        vr = VersionRecord(
            passport_id=str(student["passport_id"]),
            email=str(student["email"]),
            version_number=int(cast(int, row["version_number"])),
            holder_name=str(row["holder_name"]),
            verification_code=str(row["verification_code"]),
            verification_id_hash=str(row["verification_id_hash"]),
            skill_fingerprint=str(row["skill_fingerprint"]),
            content_hash=str(row["content_hash"]),
            anchor_status=str(row["anchor_status"]),
            pdf_en_path=None,
            pdf_ka_path=None,
            tx_hash=None if tx_hash is None else str(tx_hash),
            issued_at=str(issued_raw),
            skills=skills,
            anchored_at=None if anchored_at is None else str(anchored_at),
        )

        chain = chain_from_settings()
        if chain is None:
            return {"status": "no_chain_configured"}

        try:
            publish_anchor(vr, chain, now=_now())
        except Exception:
            vr.anchor_status = "failed"
            vr.anchored_at = None

        get_supabase().table("passport_versions").update(
            {
                "anchor_status": vr.anchor_status,
                "tx_hash": vr.tx_hash,
                "anchored_at": vr.anchored_at,
            }
        ).eq("id", version_id).execute()

        return {"status": vr.anchor_status}
    except RuntimeError as exc:
        if "supabase_not_configured" in str(exc):
            return _demo_store.retry_anchor(version_id)
        raise


@router.post("/versions/{version_id}/pdf", status_code=200)
def regenerate_pdf(
    version_id: str,
    force: bool = Query(default=False),
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    require_admin(authorization)
    resp = (
        get_supabase()
        .table("passport_versions")
        .select(
            "id, version_number, holder_name, verification_code, issued_at, "
            "pdf_en_path, pdf_ka_path, "
            "skill_entries(skill, badge, awarded_on, description, position), "
            "students(email, passport_id)"
        )
        .eq("id", version_id)
        .limit(1)
        .execute()
    )
    rows = _table_rows(resp.data)
    if not rows:
        raise APIError(404, "version_not_found")
    row = rows[0]

    has_en = row.get("pdf_en_path") is not None
    has_ka = row.get("pdf_ka_path") is not None
    if has_en and has_ka and not force:
        raise APIError(409, "pdf_already_exists")

    student_embed = row.get("students")
    if isinstance(student_embed, list):
        student_embed = student_embed[0] if student_embed else None
    if not isinstance(student_embed, dict):
        raise RuntimeError("student_missing")
    student = cast(dict[str, object], student_embed)

    skill_rows = sorted(
        _table_rows(row.get("skill_entries")),
        key=lambda r: int(cast(int, r.get("position", 0))),
    )
    skills = tuple(
        Skill(
            skill=str(r["skill"]),
            badge=str(r["badge"]),
            awarded_on=None if r.get("awarded_on") is None else str(r["awarded_on"]),
            description=str(r.get("description") or ""),
        )
        for r in skill_rows
    )

    issued_raw = row.get("issued_at") or _now()
    storage = get_storage()
    en_path, ka_path = publish_pdfs(
        PassportPdf(
            holder_name=str(row["holder_name"]),
            passport_id=str(student["passport_id"]),
            version=int(cast(int, row["version_number"])),
            issued_on=str(issued_raw)[:10],
            verification_code=str(row["verification_code"]),
            skills=skills,
        ),
        storage,
    )
    get_supabase().table("passport_versions").update(
        {"pdf_en_path": en_path, "pdf_ka_path": ka_path}
    ).eq("id", version_id).execute()
    return {"en_path": en_path, "ka_path": ka_path}
