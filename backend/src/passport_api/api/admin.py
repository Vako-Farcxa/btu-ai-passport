"""Admin API router.

All endpoints require a valid btu.edu.ge JWT whose email is in admin_users.
Sheet-managed students (admin_managed=False) are read-only from the admin
panel's perspective — their skills can only be changed via the Google Sheet.
"""

from postgrest import CountMethod

import unicodedata
from datetime import UTC, datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Header, Query
from fastapi.responses import Response

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
    AdminSkillAdd,
    AdminSkillEntry,
    AdminStudent,
    AdminStudentCreate,
    AdminStudentDetail,
    AdminStudentList,
    AdminSyncRun,
    AdminSyncRunList,
    AdminVersion,
    AdminVersionPending,
    AdminVersionPendingList,
    Skill,
    SyncResult,
)
from passport_api.sync import (
    GspreadSheet,
    SupabaseSyncStore,
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


@router.get("/students/{passport_id}", response_model=AdminStudentDetail)
def get_student(
    passport_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> AdminStudentDetail:
    require_admin(authorization)
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


# ---------------------------------------------------------------------------
# Students — write
# ---------------------------------------------------------------------------


@router.post("/students", response_model=AdminStudentDetail, status_code=201)
def create_student(
    body: AdminStudentCreate,
    authorization: Annotated[str | None, Header()] = None,
) -> AdminStudentDetail:
    require_admin(authorization)

    email = _nfc(str(body.email)).lower()
    if not email.endswith("@btu.edu.ge"):
        raise APIError(422, "domain_not_allowed")

    # Check uniqueness
    existing = get_supabase().table("students").select("id").eq("email", email).limit(1).execute()
    if _table_rows(existing.data):
        raise APIError(409, "student_email_taken")

    # Generate a unique passport_id
    taken_resp = get_supabase().table("students").select("passport_id").execute()
    taken_ids: set[str] = {str(r["passport_id"]) for r in _table_rows(taken_resp.data)}

    import secrets  # noqa: PLC0415

    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    for _ in range(32):
        raw = "".join(secrets.choice(alphabet) for _ in range(10))
        pid = f"BTU-{raw}"
        if pid not in taken_ids:
            break
    else:
        raise RuntimeError("passport_id_exhausted")

    resp = (
        get_supabase()
        .table("students")
        .insert(
            {
                "email": email,
                "full_name": _nfc(body.full_name),
                "passport_id": pid,
                "admin_managed": True,
            }
        )
        .execute()
    )
    rows = _table_rows(resp.data)
    if not rows:
        raise RuntimeError("student_not_created")

    return get_student(pid, authorization)


@router.delete("/students/{passport_id}", status_code=204)
def delete_student(
    passport_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    require_admin(authorization)
    student = _require_admin_student(passport_id)
    if student.get("deleted_at") is not None:
        raise APIError(409, "student_already_deleted")
    get_supabase().table("students").update({"deleted_at": _now()}).eq(
        "id", str(student["id"])
    ).execute()
    return Response(status_code=204)


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


# ---------------------------------------------------------------------------
# Sync operations
# ---------------------------------------------------------------------------


@router.get("/sync-runs", response_model=AdminSyncRunList)
def list_sync_runs(
    authorization: Annotated[str | None, Header()] = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> AdminSyncRunList:
    require_admin(authorization)
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
                rows_read=None if r.get("rows_read") is None else int(cast(int, r["rows_read"])),
                versions_created=(
                    None
                    if r.get("versions_created") is None
                    else int(cast(int, r["versions_created"]))
                ),
                error=None if r.get("error") is None else str(r["error"]),
            )
        )
    return AdminSyncRunList(runs=runs)


@router.post("/sync", response_model=SyncResult)
def trigger_sync(
    authorization: Annotated[str | None, Header()] = None,
) -> SyncResult:
    require_admin(authorization)
    store = SupabaseSyncStore()
    sheet = GspreadSheet()
    return run_sync(store, sheet)


# ---------------------------------------------------------------------------
# Anchor operations
# ---------------------------------------------------------------------------


@router.get("/versions/pending", response_model=AdminVersionPendingList)
def list_pending_versions(
    authorization: Annotated[str | None, Header()] = None,
) -> AdminVersionPendingList:
    require_admin(authorization)
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


@router.post("/versions/{version_id}/anchor", status_code=200)
def retry_anchor(
    version_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    require_admin(authorization)
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
