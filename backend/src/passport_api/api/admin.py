"""Admin API router.

Every route here sits behind the router-level `_admin_guard` dependency: a valid Supabase
JWT with an allowed email that is listed in admin_users. The guard runs before request
bodies are validated, so a caller without it gets 401 or 403 and nothing else.
Sheet-managed students (admin_managed=False) are read-only from the admin
panel's perspective — their skills can only be changed via the Google Sheet.
"""

import logging
import re
import unicodedata
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import Response
from postgrest import CountMethod

from passport_api.admin_health import load_admin_health
from passport_api.anchoring import reconcile_anchors
from passport_api.api.sync import get_sync_store
from passport_api.auth import require_admin
from passport_api.chain import chain_from_settings
from passport_api.consistency import find_inconsistencies, load_students
from passport_api.db import get_supabase
from passport_api.errors import APIError
from passport_api.pdf import PassportPdf, get_storage, publish_pdfs
from passport_api.ratelimit import enforce
from passport_api.schemas import (
    AdminAwardRequest,
    AdminAwardResponse,
    AdminCatalogSkill,
    AdminCatalogSkillCreate,
    AdminCatalogSkillList,
    AdminCatalogSkillUpdate,
    AdminHealth,
    AdminMe,
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
    ConsistencyProblem,
    ConsistencyReport,
    Skill,
    SyncResult,
)
from passport_api.search import contains_filter
from passport_api.settings import settings
from passport_api.sheet_admin import (
    ALREADY_AWARDED,
    AdminGspreadSheet,
    AdminSheet,
    AwardInput,
)
from passport_api.store import normalize_anchor_status
from passport_api.sync import (
    STUDENT_ARCHIVED,
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
from passport_api.validation import (
    DUPLICATE_EMAIL,
    FIRST_NAME_INVALID,
    LAST_NAME_INVALID,
    clean_email,
    clean_name,
    email_error,
    name_error,
)

_log = logging.getLogger(__name__)


def _admin_guard(authorization: Annotated[str | None, Header()] = None) -> str:
    return require_admin(authorization)


_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def admin_write_limit(request: Request, email: Annotated[str, Depends(_admin_guard)]) -> None:
    """Every admin write (not reads) counts against a per-admin limit, 30 a minute by default.

    It runs after the guard, so only real admins are counted, by email and not by IP.
    """
    if request.method in _WRITE_METHODS:
        enforce("admin_write", email, settings.rate_limit_admin_writes_per_minute)


# Shared with the admin flags router so every /admin write has the same guard and limit.
ADMIN_DEPENDENCIES = [Depends(_admin_guard), Depends(admin_write_limit)]

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=ADMIN_DEPENDENCIES)


@router.get("/me", response_model=AdminMe)
def admin_me(email: Annotated[str, Depends(_admin_guard)]) -> AdminMe:
    """Lets the admin UI ask "am I an admin?" before it shows anything."""
    return AdminMe(email=email)


@router.get("/health", response_model=AdminHealth)
def admin_health() -> AdminHealth:
    """Everything that needs attention right now, for the dashboard banner. Read only."""
    try:
        return load_admin_health()
    except Exception as exc:
        _log.exception("admin_health_failed")
        raise APIError(503, "health_unavailable") from exc


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
        anchor_status=normalize_anchor_status(str(row["anchor_status"])),
        anchor_attempts=int(cast(int, row.get("anchor_attempts") or 0)),
        anchor_last_error=(
            None if row.get("anchor_last_error") is None else str(row["anchor_last_error"])
        ),
        tx_hash=None if row.get("tx_hash") is None else str(row["tx_hash"]),
        issued_at=datetime.fromisoformat(str(issued_raw).replace("Z", "+00:00")),
        pdf_en_path=None if row.get("pdf_en_path") is None else str(row["pdf_en_path"]),
        pdf_ka_path=None if row.get("pdf_ka_path") is None else str(row["pdf_ka_path"]),
        revoked_at=_optional_datetime(row.get("revoked_at")),
        skills=skills,
    )


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


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
        latest_anchor_status=None
        if latest_anchor is None
        else normalize_anchor_status(latest_anchor),
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


# ---------------------------------------------------------------------------
# Students — read
# ---------------------------------------------------------------------------


@router.get("/students", response_model=AdminStudentList)
def list_students(
    search: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> AdminStudentList:
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
    search_filter = contains_filter(["email", "full_name"], search) if search else None
    if search_filter:
        query = query.or_(search_filter)
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
) -> AdminStudentDetail:
    student = _require_admin_student(passport_id)
    versions_resp = (
        get_supabase()
        .table("passport_versions")
        .select(
            "id, version_number, holder_name, verification_code, anchor_status, "
            "tx_hash, issued_at, pdf_en_path, pdf_ka_path, revoked_at, "
            "anchor_attempts, anchor_last_error, "
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
# Students — write (new students are created by awarding a skill, see /admin/awards)
# ---------------------------------------------------------------------------


@router.delete("/students/{passport_id}", status_code=204)
def delete_student(
    passport_id: str,
) -> Response:
    student = _require_admin_student(passport_id)
    if student.get("deleted_at") is not None:
        raise APIError(409, "student_already_deleted")
    get_supabase().table("students").update({"deleted_at": _now()}).eq(
        "id", str(student["id"])
    ).execute()
    return Response(status_code=204)


@router.post("/students/{passport_id}/restore", status_code=204)
def restore_student(
    passport_id: str,
) -> Response:
    """Un-archive a student: their codes verify again and they can open their passport."""
    student = _require_admin_student(passport_id)
    if student.get("deleted_at") is None:
        raise APIError(409, "student_not_deleted")
    get_supabase().table("students").update({"deleted_at": None}).eq(
        "id", str(student["id"])
    ).execute()
    return Response(status_code=204)


def _require_version(version_id: str) -> dict[str, object]:
    response = (
        get_supabase()
        .table("passport_versions")
        .select("id, revoked_at")
        .eq("id", version_id)
        .limit(1)
        .execute()
    )
    rows = _table_rows(response.data)
    if not rows:
        raise APIError(404, "version_not_found")
    return rows[0]


@router.post("/versions/{version_id}/revoke", status_code=204)
def revoke_version(
    version_id: str,
) -> Response:
    """Revoke one version. Its code verifies as Revoked and its PDF can no longer be
    downloaded. Newer and older versions are not touched."""
    version = _require_version(version_id)
    if version.get("revoked_at") is not None:
        raise APIError(409, "version_already_revoked")
    get_supabase().table("passport_versions").update({"revoked_at": _now()}).eq(
        "id", version_id
    ).execute()
    return Response(status_code=204)


@router.post("/versions/{version_id}/unrevoke", status_code=204)
def unrevoke_version(
    version_id: str,
) -> Response:
    version = _require_version(version_id)
    if version.get("revoked_at") is None:
        raise APIError(409, "version_not_revoked")
    get_supabase().table("passport_versions").update({"revoked_at": None}).eq(
        "id", version_id
    ).execute()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Sync operations
# ---------------------------------------------------------------------------


@router.get("/sync-runs", response_model=AdminSyncRunList)
def list_sync_runs(
    limit: int = Query(default=50, ge=1, le=200),
) -> AdminSyncRunList:
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
                rows_read=(None if r.get("rows_read") is None else int(cast(int, r["rows_read"]))),
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
def trigger_sync() -> SyncResult:
    return run_sync(SupabaseSyncStore(), GspreadSheet())


# ---------------------------------------------------------------------------
# Skills catalog (Skills tab first, then the skills table)
# ---------------------------------------------------------------------------

_SKILL_COLUMNS = "id, name, name_ka, category, badge, description"
_SKILL_ID = re.compile(r"^SKL-(\d+)$")


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
def list_skills() -> AdminCatalogSkillList:
    return AdminCatalogSkillList(skills=_db_skills())


@router.post("/skills", response_model=AdminCatalogSkill, status_code=201)
def create_skill(
    body: AdminCatalogSkillCreate,
    sheet: AdminSheet = _admin_sheet_dependency,
) -> AdminCatalogSkill:
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
    sheet: AdminSheet = _admin_sheet_dependency,
) -> AdminCatalogSkill:
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
    sheet: AdminSheet = _admin_sheet_dependency,
    store: SyncStore = _sync_store_dependency,
) -> AdminAwardResponse:
    emails = [clean_email(student.email) for student in body.students]
    if len(set(emails)) != len(emails):
        raise APIError(422, DUPLICATE_EMAIL)
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

    known = store.current_students()
    order: list[str] = []
    results: dict[str, AwardRowResult] = {}
    awards: list[AwardInput] = []
    for student in body.students:
        email = clean_email(student.email)
        order.append(email)
        first_name, last_name = clean_name(student.first_name), clean_name(student.last_name)
        problem = email_error(email)
        if problem is None and email in known and known[email].archived:
            problem = STUDENT_ARCHIVED
        if problem is None and (first_name or last_name):
            # A name is optional only when neither part is given (an existing student).
            problem = name_error(first_name, FIRST_NAME_INVALID) or name_error(
                last_name, LAST_NAME_INVALID
            )
        if problem is not None:
            results[email] = AwardRowResult(email=email, status="failed", error=problem)
            continue
        awards.append(
            AwardInput(
                email=email,
                passport_id=known[email].passport_id if email in known else "",
                first_name=first_name,
                last_name=last_name,
                program=_nfc(student.program),
                education_level=_nfc(student.education_level),
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
            placements = sheet.append_awards(awards, set(known))
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
        if sync_result.status == "skipped":
            # Another sync holds the lock. The rows are already in the Sheet.
            sync_result = sync_result.model_copy(update={"error": "sync_in_progress"})
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
def list_pending_versions() -> AdminVersionPendingList:
    resp = (
        get_supabase()
        .table("passport_versions")
        .select(
            "id, version_number, holder_name, anchor_status, tx_hash, issued_at, "
            "anchor_attempts, anchor_last_error, anchor_submitted_at, anchor_next_attempt_at, "
            "students(passport_id)"
        )
        .neq("anchor_status", "confirmed")
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
        status = normalize_anchor_status(str(r["anchor_status"]))
        if status == "confirmed":
            continue
        versions.append(
            AdminVersionPending(
                version_id=cast(str, r["id"]),
                passport_id=passport_id,
                holder_name=str(r["holder_name"]),
                version_number=int(cast(int, r["version_number"])),
                anchor_status=status,
                issued_at=datetime.fromisoformat(str(issued_raw).replace("Z", "+00:00")),
                tx_hash=None if r.get("tx_hash") is None else str(r["tx_hash"]),
                anchor_attempts=int(cast(int, r.get("anchor_attempts") or 0)),
                anchor_last_error=(
                    None if r.get("anchor_last_error") is None else str(r["anchor_last_error"])
                ),
                anchor_submitted_at=_optional_datetime(r.get("anchor_submitted_at")),
                anchor_next_attempt_at=_optional_datetime(r.get("anchor_next_attempt_at")),
            )
        )
    return AdminVersionPendingList(versions=versions)


@router.get("/consistency", response_model=ConsistencyReport)
def consistency_report() -> ConsistencyReport:
    """Students and versions left half-written by the old non-atomic sync. Read only."""
    students = load_students()
    return ConsistencyReport(
        students_checked=len(students),
        problems=[
            ConsistencyProblem(
                kind=problem.kind,
                passport_id=problem.passport_id,
                version_number=problem.version_number,
                detail=problem.detail,
            )
            for problem in find_inconsistencies(students)
        ],
    )


@router.post("/versions/{version_id}/anchor", status_code=200)
def retry_anchor(
    version_id: str,
) -> dict[str, str]:
    """Retry anchoring one version now.

    This resets the attempt counter and the backoff, then runs the same reconciler the cron
    uses. It first checks the receipts of every transaction already sent and the contract
    slot, so pressing it can never anchor the same hash twice.
    """
    from passport_api.sync import SupabaseSyncStore  # noqa: PLC0415

    store = SupabaseSyncStore()
    record = store.version_by_id(version_id)
    if record is None:
        raise APIError(404, "version_not_found")
    if record.anchor_status == "confirmed":
        raise APIError(409, "anchor_already_confirmed")

    chain = chain_from_settings()
    if chain is None:
        return {"status": "no_chain_configured"}

    result = reconcile_anchors(store, chain, only=[record], force=True)
    if result.status == "skipped":
        raise APIError(409, "anchor_busy")
    status = normalize_anchor_status(record.anchor_status)
    response: dict[str, str] = {"status": status}
    if record.anchor_last_error and status != "confirmed":
        response["error"] = record.anchor_last_error
    elif result.error:
        response["error"] = result.error
    return response


@router.post("/versions/{version_id}/pdf", status_code=200)
def regenerate_pdf(
    version_id: str,
    force: bool = Query(default=False),
) -> dict[str, str]:
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
