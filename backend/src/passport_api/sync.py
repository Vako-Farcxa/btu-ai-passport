import hashlib
import json
import logging
import secrets
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast

import gspread
from postgrest.exceptions import APIError

from passport_api.chain import AnchorChain, chain_from_settings, publish_anchor
from passport_api.db import get_supabase
from passport_api.fingerprint import (
    canonical_skills,
    content_hash,
    normalize_awarded_on,
    skill_fingerprint,
    verification_id_hash,
)
from passport_api.pdf import PassportPdf, get_storage, publish_pdfs
from passport_api.schemas import Skill, SyncResult
from passport_api.settings import email_domain_allowed, settings

_log = logging.getLogger(__name__)
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_COLUMNS = (
    "email",
    "full_name",
    "skill",
    "badge",
    "awarded_on",
    "passport_id",
    "description",
    "skill_id",
    "skill_category",
)
_SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
# Header aliases, lowercased. The first name in each tuple is the old 5-column format.
_ALIASES: dict[str, tuple[str, ...]] = {
    "email": ("email", "btu email (test)", "btu email", "student email"),
    "full_name": ("full_name", "full name"),
    "first_name": ("first name", "first_name"),
    "last_name": ("last name", "last_name"),
    "skill": ("skill", "skill name", "skill_name"),
    "badge": ("badge", "badge/stamp code", "badge code", "stamp code"),
    "awarded_on": ("awarded_on", "date earned", "date_earned"),
    "passport_id": ("passport_id", "passport id (existing)", "passport id"),
    "skill_id": ("skill id", "skill_id"),
    "skill_category": ("skill category", "skill_category"),
    "description": ("skill description", "skill_description", "description"),
}
# Sync output columns written back by the service (official sheet Q-T, plus G).
STATUS_SYNCED = "SYNCED"
STATUS_FAILED = "FAILED"
_WRITE_COLUMNS: dict[str, tuple[str, ...]] = {
    "status": ("passport sync status",),
    "version": ("synced passport version",),
    "synced_at": ("synced at (utc)", "synced at"),
    "error": ("sync error / notes", "sync error"),
    "passport_id": _ALIASES["passport_id"][1:],
}
_CATEGORY_BADGES = {
    "ai skill": "BDG-AI-001",
    "ai applied skill": "BDG-AI-002",
    "ai advanced skill": "BDG-AI-003",
}


@dataclass(frozen=True)
class CatalogSkill:
    """One row of the skills catalog, taken from the sheet's Skill ID column."""

    id: str
    name: str
    category: str
    badge: str
    description: str
    # Georgian name from the Skills tab. None means "leave the stored value alone".
    name_ka: str | None = None


SKILLS_TAB = "Skills"
SKILLS_HEADER = ("skill_id", "name_en", "name_ka", "category", "description")


def badge_for_category(category: str) -> str:
    return _CATEGORY_BADGES.get(category.strip().lower(), "")


def catalog_from_values(values: list[list[object]]) -> list[CatalogSkill]:
    """Skills from the Skills tab grid. The header row is the first row with skill_id."""
    header_index = next(
        (
            index
            for index, row in enumerate(values)
            if "skill_id" in {_cell(cell).lower() for cell in row}
        ),
        None,
    )
    if header_index is None:
        return []
    columns = {
        _cell(cell).lower(): position
        for position, cell in reversed(list(enumerate(values[header_index])))
        if _cell(cell)
    }
    skills: list[CatalogSkill] = []
    for row in values[header_index + 1 :]:
        skill_id = _tab_field(row, columns, "skill_id").upper()
        name = _tab_field(row, columns, "name_en")
        if not skill_id or not name:
            continue
        category = _tab_field(row, columns, "category")
        skills.append(
            CatalogSkill(
                id=skill_id,
                name=name,
                category=category,
                badge=badge_for_category(category),
                description=_tab_field(row, columns, "description"),
                name_ka=_tab_field(row, columns, "name_ka"),
            )
        )
    return skills


def _tab_field(row: list[object], columns: dict[str, int], name: str) -> str:
    position = columns.get(name)
    return _cell(row[position]) if position is not None and position < len(row) else ""


class SheetUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class RowOutcome:
    """Sync result for one data row, by its index in read_rows()."""

    index: int
    status: str
    version: str
    synced_at: str
    error: str
    passport_id: str


class Sheet(Protocol):
    def read_rows(self) -> list[dict[str, object]]: ...

    def write_back(self, outcomes: list[RowOutcome]) -> None: ...


def find_header_row(values: list[list[object]]) -> int | None:
    """Index of the first row that has an email column, or None."""
    for index, row in enumerate(values):
        names = {_cell(cell).lower() for cell in row}
        if names & set(_ALIASES["email"]):
            return index
    return None


def records_from_values(values: list[list[object]]) -> tuple[list[str], list[dict[str, object]]]:
    """Header and data records from a raw grid. Title rows above the header are skipped."""
    header_index = find_header_row(values)
    if header_index is None:
        return [], []
    header = [_cell(cell) for cell in values[header_index]]
    records: list[dict[str, object]] = []
    for row in values[header_index + 1 :]:
        record: dict[str, object] = {}
        for position, name in enumerate(header):
            if name:
                record[name] = row[position] if position < len(row) else ""
        records.append(record)
    return header, records


@dataclass
class StudentRecord:
    email: str
    full_name: str
    passport_id: str


@dataclass
class VersionRecord:
    passport_id: str
    email: str
    version_number: int
    holder_name: str
    verification_code: str
    verification_id_hash: str
    skill_fingerprint: str
    content_hash: str
    anchor_status: str
    pdf_en_path: str | None
    pdf_ka_path: str | None
    tx_hash: str | None
    issued_at: str
    skills: tuple[Skill, ...]
    anchored_at: str | None = None


@dataclass(frozen=True)
class PendingPdf:
    email: str
    passport_id: str
    version_number: int
    holder_name: str
    verification_code: str
    issued_at: str
    skills: tuple[Skill, ...]


@dataclass
class RunRecord:
    status: str
    rows_read: int
    versions_created: int
    error: str | None


@dataclass(frozen=True)
class StudentState:
    email: str
    full_name: str
    passport_id: str
    latest_version: int
    latest_fingerprint: str
    holder_name: str


@dataclass
class _SkillFact:
    skill: str
    badge: str
    awarded_on: str | None
    raw_awarded_on: str
    description: str = ""
    skill_id: str = ""
    category: str = ""


@dataclass
class _EmailGroup:
    full_name: str
    rows: list[_SkillFact]
    indexes: list[int]
    passport_id: str = ""


class SyncStore(Protocol):
    def has_running(self) -> bool: ...

    def try_acquire(self) -> bool: ...

    def record_skipped(self) -> None: ...

    def abort(self) -> None: ...

    def finish(self, rows_read: int, versions_created: int) -> None: ...

    def current_students(self) -> dict[str, StudentState]: ...

    def save_student_name(self, email: str, full_name: str) -> None: ...

    def insert_student(self, email: str, full_name: str, passport_id: str) -> None: ...

    def insert_version(self, version: VersionRecord) -> None: ...

    def upsert_skills(self, skills: list[CatalogSkill]) -> None: ...

    def remember_source(self, record_key: str, email: str) -> None: ...

    def taken_passport_ids(self) -> set[str]: ...

    def taken_verification_codes(self) -> set[str]: ...

    def taken_content_hashes(self) -> set[str]: ...

    def pending_pdfs(self) -> list[PendingPdf]: ...

    def save_pdf_paths(
        self, email: str, version_number: int, en_path: str, ka_path: str
    ) -> None: ...

    def pending_anchors(self) -> list[VersionRecord]: ...

    def save_anchor(
        self,
        email: str,
        version_number: int,
        *,
        status: str,
        tx_hash: str | None,
        anchored_at: str | None,
    ) -> None: ...


class FakeSheet:
    def __init__(
        self,
        rows: list[dict[str, str]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._rows = [] if rows is None else rows
        self._error = error
        self.reads = 0
        self.writes: list[list[RowOutcome]] = []

    def read_rows(self) -> list[dict[str, object]]:
        self.reads += 1
        if self._error is not None:
            raise self._error
        return [dict(row) for row in self._rows]

    def write_back(self, outcomes: list[RowOutcome]) -> None:
        self.writes.append(list(outcomes))


def open_spreadsheet() -> Any:
    """The configured Google spreadsheet, opened with the service account."""
    if not settings.sheet_id or not settings.google_service_account_json:
        raise SheetUnavailableError("sheet_not_configured")
    try:
        parsed = json.loads(settings.google_service_account_json)
    except json.JSONDecodeError as exc:
        raise SheetUnavailableError("sheet_not_configured") from exc
    if not isinstance(parsed, dict):
        raise SheetUnavailableError("sheet_not_configured")
    info = cast(dict[str, Any], parsed)
    key = info.get("private_key")
    if isinstance(key, str) and "\\n" in key:
        # Hosting dashboards often keep escaped newlines in pasted JSON.
        info["private_key"] = key.replace("\\n", "\n")
    try:
        client = gspread.service_account_from_dict(info, scopes=_SHEETS_SCOPES)
        return client.open_by_key(settings.sheet_id)
    except Exception as exc:
        _log.warning("sheet_read_failed: %s", type(exc).__name__, exc_info=True)
        raise SheetUnavailableError("sheet_unavailable") from exc


class GspreadSheet:
    def __init__(self) -> None:
        self._worksheet: Any = None
        self._header: list[str] = []
        self._first_data_row = 0

    def read_rows(self) -> list[dict[str, object]]:
        spreadsheet = open_spreadsheet()
        try:
            worksheet = spreadsheet.get_worksheet(0)
            values = worksheet.get_all_values()
        except Exception as exc:
            _log.warning("sheet_read_failed: %s", type(exc).__name__, exc_info=True)
            raise SheetUnavailableError("sheet_unavailable") from exc
        grid = cast(list[list[object]], values)
        header_index = find_header_row(grid)
        header, records = records_from_values(grid)
        self._worksheet = worksheet
        self._header = header
        self._first_data_row = 0 if header_index is None else header_index + 2
        return records

    def read_catalog(self) -> list[CatalogSkill]:
        """Skills from the optional Skills tab. Empty when the tab does not exist."""
        spreadsheet = open_spreadsheet()
        try:
            worksheet = spreadsheet.worksheet(SKILLS_TAB)
        except gspread.WorksheetNotFound:
            return []
        except Exception as exc:
            _log.warning("catalog_read_failed: %s", type(exc).__name__, exc_info=True)
            raise SheetUnavailableError("sheet_unavailable") from exc
        return catalog_from_values(cast(list[list[object]], worksheet.get_all_values()))

    def write_back(self, outcomes: list[RowOutcome]) -> None:
        if self._worksheet is None or not outcomes:
            return
        updates = write_back_ranges(self._header, self._first_data_row, outcomes)
        if updates:
            self._worksheet.batch_update(updates, value_input_option="RAW")


def write_back_ranges(
    header: list[str], first_data_row: int, outcomes: list[RowOutcome]
) -> list[dict[str, object]]:
    """A1 updates for the sync output columns that exist in this header."""
    lowered = [name.strip().lower() for name in header]
    columns: dict[str, int] = {}
    for field, names in _WRITE_COLUMNS.items():
        for position, name in enumerate(lowered):
            if name in names:
                columns[field] = position
                break
    updates: list[dict[str, object]] = []
    for outcome in outcomes:
        row_number = first_data_row + outcome.index
        values = {
            "status": outcome.status,
            "version": outcome.version,
            "synced_at": outcome.synced_at,
            "error": outcome.error,
            "passport_id": outcome.passport_id,
        }
        for field, position in columns.items():
            if field == "passport_id" and not outcome.passport_id:
                continue
            cell = gspread.utils.rowcol_to_a1(row_number, position + 1)
            updates.append({"range": cell, "values": [[values[field]]]})
    return updates


class MemorySyncStore:
    def __init__(self) -> None:
        self.students: list[StudentRecord] = []
        self.versions: list[VersionRecord] = []
        self.runs: list[RunRecord] = []
        self.skills: dict[str, CatalogSkill] = {}
        self._sources: dict[str, str] = {}

    def has_running(self) -> bool:
        return any(run.status == "running" for run in self.runs)

    def try_acquire(self) -> bool:
        if self.has_running():
            return False
        self.runs.append(RunRecord(status="running", rows_read=0, versions_created=0, error=None))
        return True

    def record_skipped(self) -> None:
        self.runs.append(RunRecord(status="skipped", rows_read=0, versions_created=0, error=None))

    def abort(self) -> None:
        self._close("failed", 0, 0, "sheet_unavailable")

    def finish(self, rows_read: int, versions_created: int) -> None:
        self._close("completed", rows_read, versions_created, None)

    def current_students(self) -> dict[str, StudentState]:
        latest: dict[str, VersionRecord] = {}
        for version in self.versions:
            current = latest.get(version.email)
            if current is None or version.version_number > current.version_number:
                latest[version.email] = version
        states: dict[str, StudentState] = {}
        for student in self.students:
            latest_version = latest.get(student.email)
            if latest_version is None:
                continue
            states[student.email] = StudentState(
                email=student.email,
                full_name=student.full_name,
                passport_id=student.passport_id,
                latest_version=latest_version.version_number,
                latest_fingerprint=latest_version.skill_fingerprint,
                holder_name=latest_version.holder_name,
            )
        return states

    def save_student_name(self, email: str, full_name: str) -> None:
        for student in self.students:
            if student.email == email:
                student.full_name = full_name
                return

    def insert_student(self, email: str, full_name: str, passport_id: str) -> None:
        self.students.append(
            StudentRecord(email=email, full_name=full_name, passport_id=passport_id)
        )

    def insert_version(self, version: VersionRecord) -> None:
        for skill in version.skills:
            if skill.skill_id is not None and skill.skill_id not in self.skills:
                raise RuntimeError("skill_not_in_catalog")
        self.versions.append(version)

    def upsert_skills(self, skills: list[CatalogSkill]) -> None:
        for skill in skills:
            self.skills[skill.id] = skill

    def remember_source(self, record_key: str, email: str) -> None:
        self._sources[record_key] = email

    def taken_passport_ids(self) -> set[str]:
        return {student.passport_id for student in self.students}

    def taken_verification_codes(self) -> set[str]:
        return {version.verification_code for version in self.versions}

    def taken_content_hashes(self) -> set[str]:
        return {version.content_hash for version in self.versions}

    def pending_pdfs(self) -> list[PendingPdf]:
        return [
            PendingPdf(
                email=version.email,
                passport_id=version.passport_id,
                version_number=version.version_number,
                holder_name=version.holder_name,
                verification_code=version.verification_code,
                issued_at=version.issued_at,
                skills=version.skills,
            )
            for version in self.versions
            if version.pdf_en_path is None or version.pdf_ka_path is None
        ]

    def save_pdf_paths(self, email: str, version_number: int, en_path: str, ka_path: str) -> None:
        for version in self.versions:
            if version.email == email and version.version_number == version_number:
                version.pdf_en_path = en_path
                version.pdf_ka_path = ka_path
                return
        raise RuntimeError("version_missing")

    def pending_anchors(self) -> list[VersionRecord]:
        return [version for version in self.versions if version.anchor_status != "confirmed"]

    def save_anchor(
        self,
        email: str,
        version_number: int,
        *,
        status: str,
        tx_hash: str | None,
        anchored_at: str | None,
    ) -> None:
        for version in self.versions:
            if version.email == email and version.version_number == version_number:
                version.anchor_status = status
                version.tx_hash = tx_hash
                version.anchored_at = anchored_at
                return
        raise RuntimeError("version_missing")

    def _close(self, status: str, rows_read: int, versions_created: int, error: str | None) -> None:
        for run in reversed(self.runs):
            if run.status == "running":
                run.status = status
                run.rows_read = rows_read
                run.versions_created = versions_created
                run.error = error
                return
        raise RuntimeError("no_running_sync")


class SupabaseSyncStore:
    def __init__(self) -> None:
        self._running_id: str | None = None

    def has_running(self) -> bool:
        response = (
            get_supabase()
            .table("sync_runs")
            .select("id")
            .eq("status", "running")
            .limit(1)
            .execute()
        )
        return bool(_table_rows(response.data))

    def try_acquire(self) -> bool:
        if self.has_running():
            return False
        try:
            response = get_supabase().table("sync_runs").insert({"status": "running"}).execute()
        except APIError as exc:
            if exc.code == "23505":
                return False
            raise
        rows = _table_rows(response.data)
        if not rows:
            raise RuntimeError("sync_run_not_created")
        self._running_id = str(rows[0]["id"])
        return True

    def record_skipped(self) -> None:
        get_supabase().table("sync_runs").insert(
            {
                "status": "skipped",
                "rows_read": 0,
                "versions_created": 0,
                "finished_at": _now(),
            }
        ).execute()

    def abort(self) -> None:
        self._update_running("failed", 0, 0, "sheet_unavailable")

    def finish(self, rows_read: int, versions_created: int) -> None:
        self._update_running("completed", rows_read, versions_created, None)

    def current_students(self) -> dict[str, StudentState]:
        response = (
            get_supabase()
            .table("students")
            .select(
                "email, full_name, passport_id, "
                "passport_versions(version_number, skill_fingerprint, holder_name)"
            )
            .eq("admin_managed", False)
            .is_("deleted_at", "null")
            .execute()
        )
        states: dict[str, StudentState] = {}
        for row in _table_rows(response.data):
            versions = _nested_rows(row.get("passport_versions"))
            if not versions:
                continue
            latest = max(versions, key=lambda item: _as_int(item["version_number"]))
            email = str(row["email"])
            states[email] = StudentState(
                email=email,
                full_name=str(row["full_name"]),
                passport_id=str(row["passport_id"]),
                latest_version=_as_int(latest["version_number"]),
                latest_fingerprint=str(latest["skill_fingerprint"]),
                holder_name=str(latest["holder_name"]),
            )
        return states

    def save_student_name(self, email: str, full_name: str) -> None:
        get_supabase().table("students").update({"full_name": full_name, "updated_at": _now()}).eq(
            "email", email
        ).execute()

    def insert_student(self, email: str, full_name: str, passport_id: str) -> None:
        get_supabase().table("students").insert(
            {"email": email, "full_name": full_name, "passport_id": passport_id}
        ).execute()

    def insert_version(self, version: VersionRecord) -> None:
        student_id = self._student_id(version.email)
        response = (
            get_supabase()
            .table("passport_versions")
            .insert(
                {
                    "student_id": student_id,
                    "version_number": version.version_number,
                    "holder_name": version.holder_name,
                    "verification_code": version.verification_code,
                    "verification_id_hash": version.verification_id_hash,
                    "skill_fingerprint": version.skill_fingerprint,
                    "content_hash": version.content_hash,
                    "anchor_status": "pending",
                    "issued_at": version.issued_at,
                }
            )
            .execute()
        )
        rows = _table_rows(response.data)
        if not rows:
            raise RuntimeError("version_not_created")
        version_id = str(rows[0]["id"])
        skill_rows = [
            {
                "version_id": version_id,
                "skill": skill.skill,
                "badge": skill.badge,
                "awarded_on": skill.awarded_on,
                "description": skill.description,
                "skill_id": skill.skill_id,
                "position": position,
            }
            for position, skill in enumerate(version.skills, start=1)
        ]
        if skill_rows:
            get_supabase().table("skill_entries").insert(skill_rows).execute()

    def upsert_skills(self, skills: list[CatalogSkill]) -> None:
        # name_ka is sent only for skills that carry one (the Skills tab). Older databases
        # without that column keep working for sheets that have no Skills tab.
        plain = [skill for skill in skills if skill.name_ka is None]
        georgian = [skill for skill in skills if skill.name_ka is not None]
        for batch, with_ka in ((plain, False), (georgian, True)):
            if not batch:
                continue
            get_supabase().table("skills").upsert(
                [_skill_row(skill, with_ka) for skill in batch], on_conflict="id"
            ).execute()

    def remember_source(self, record_key: str, email: str) -> None:
        get_supabase().table("source_records").upsert(
            {"record_key": record_key, "email": email},
            on_conflict="record_key",
            ignore_duplicates=True,
        ).execute()

    def taken_passport_ids(self) -> set[str]:
        response = get_supabase().table("students").select("passport_id").execute()
        return {str(row["passport_id"]) for row in _table_rows(response.data)}

    def taken_verification_codes(self) -> set[str]:
        response = get_supabase().table("passport_versions").select("verification_code").execute()
        return {str(row["verification_code"]) for row in _table_rows(response.data)}

    def taken_content_hashes(self) -> set[str]:
        response = get_supabase().table("passport_versions").select("content_hash").execute()
        return {str(row["content_hash"]) for row in _table_rows(response.data)}

    def pending_pdfs(self) -> list[PendingPdf]:
        response = (
            get_supabase()
            .table("passport_versions")
            .select(
                "version_number, holder_name, verification_code, issued_at, "
                "skill_entries(skill, badge, awarded_on, description, position), "
                "students(email, passport_id)"
            )
            .or_("pdf_en_path.is.null,pdf_ka_path.is.null")
            .execute()
        )
        pending: list[PendingPdf] = []
        for row in _table_rows(response.data):
            student = _student_embed(row.get("students"))
            if student is None:
                continue
            issued_at = row.get("issued_at")
            pending.append(
                PendingPdf(
                    email=str(student["email"]),
                    passport_id=str(student["passport_id"]),
                    version_number=_as_int(row["version_number"]),
                    holder_name=str(row["holder_name"]),
                    verification_code=str(row["verification_code"]),
                    issued_at=_now() if issued_at is None else str(issued_at),
                    skills=_skills_from_rows(row.get("skill_entries")),
                )
            )
        return pending

    def save_pdf_paths(self, email: str, version_number: int, en_path: str, ka_path: str) -> None:
        student_id = self._student_id(email)
        (
            get_supabase()
            .table("passport_versions")
            .update({"pdf_en_path": en_path, "pdf_ka_path": ka_path})
            .eq("student_id", student_id)
            .eq("version_number", version_number)
            .execute()
        )

    def pending_anchors(self) -> list[VersionRecord]:
        response = (
            get_supabase()
            .table("passport_versions")
            .select(
                "version_number, holder_name, verification_code, verification_id_hash, "
                "skill_fingerprint, content_hash, anchor_status, tx_hash, anchored_at, issued_at, "
                "skill_entries(skill, badge, awarded_on, description, position), "
                "students(email, passport_id)"
            )
            .neq("anchor_status", "confirmed")
            .execute()
        )
        pending: list[VersionRecord] = []
        for row in _table_rows(response.data):
            student = _student_embed(row.get("students"))
            if student is None:
                continue
            issued_at = row.get("issued_at")
            tx_hash = row.get("tx_hash")
            anchored_at = row.get("anchored_at")
            pending.append(
                VersionRecord(
                    passport_id=str(student["passport_id"]),
                    email=str(student["email"]),
                    version_number=_as_int(row["version_number"]),
                    holder_name=str(row["holder_name"]),
                    verification_code=str(row["verification_code"]),
                    verification_id_hash=str(row["verification_id_hash"]),
                    skill_fingerprint=str(row["skill_fingerprint"]),
                    content_hash=str(row["content_hash"]),
                    anchor_status=str(row["anchor_status"]),
                    pdf_en_path=None,
                    pdf_ka_path=None,
                    tx_hash=None if tx_hash is None else str(tx_hash),
                    issued_at=_now() if issued_at is None else str(issued_at),
                    skills=_skills_from_rows(row.get("skill_entries")),
                    anchored_at=None if anchored_at is None else str(anchored_at),
                )
            )
        return pending

    def save_anchor(
        self,
        email: str,
        version_number: int,
        *,
        status: str,
        tx_hash: str | None,
        anchored_at: str | None,
    ) -> None:
        student_id = self._student_id(email)
        (
            get_supabase()
            .table("passport_versions")
            .update(
                {
                    "anchor_status": status,
                    "tx_hash": tx_hash,
                    "anchored_at": anchored_at,
                }
            )
            .eq("student_id", student_id)
            .eq("version_number", version_number)
            .execute()
        )

    def _student_id(self, email: str) -> str:
        response = (
            get_supabase().table("students").select("id").eq("email", email).limit(1).execute()
        )
        rows = _table_rows(response.data)
        if not rows:
            raise RuntimeError("student_missing")
        return str(rows[0]["id"])

    def _update_running(
        self,
        status: str,
        rows_read: int,
        versions_created: int,
        error: str | None,
    ) -> None:
        if self._running_id is None:
            raise RuntimeError("no_running_sync")
        get_supabase().table("sync_runs").update(
            {
                "status": status,
                "rows_read": rows_read,
                "versions_created": versions_created,
                "error": error,
                "finished_at": _now(),
            }
        ).eq("id", self._running_id).execute()
        self._running_id = None


def run_sync(store: SyncStore, sheet: Sheet, chain: AnchorChain | None = None) -> SyncResult:
    if not store.try_acquire():
        store.record_skipped()
        return SyncResult(status="skipped", rows_read=0, versions_created=0, error=None)
    try:
        raw_rows = sheet.read_rows()
    except Exception as exc:
        print(f"sheet_read_failed: {type(exc).__name__}: {exc}", flush=True)
        store.abort()
        return SyncResult(
            status="failed", rows_read=0, versions_created=0, error="sheet_unavailable"
        )
    outcomes: list[RowOutcome] = []
    try:
        created = _issue_versions(store, raw_rows, chain, outcomes, _read_tab_catalog(sheet))
    except Exception:
        # Release the run lock so the next scheduled sync is not blocked.
        _log.exception("sync_failed")
        store.abort()
        raise
    store.finish(len(raw_rows), created)
    try:
        sheet.write_back(sorted(outcomes, key=lambda outcome: outcome.index))
    except Exception:
        # Write-back is best effort. The passport ledger is already saved.
        _log.warning("sheet_write_back_failed", exc_info=True)
    return SyncResult(
        status="completed", rows_read=len(raw_rows), versions_created=created, error=None
    )


def _read_tab_catalog(sheet: Sheet) -> list[CatalogSkill]:
    """Skills tab rows, when the sheet has one. A failed read never blocks the sync."""
    reader = getattr(sheet, "read_catalog", None)
    if not callable(reader):
        return []
    try:
        return list(cast(list[CatalogSkill], reader()))
    except Exception:
        _log.warning("catalog_read_failed", exc_info=True)
        return []


def _issue_versions(
    store: SyncStore,
    raw_rows: list[dict[str, object]],
    chain: AnchorChain | None,
    outcomes: list[RowOutcome] | None = None,
    tab_catalog: list[CatalogSkill] | None = None,
) -> int:
    results: list[RowOutcome] = [] if outcomes is None else outcomes
    synced_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    def fail(indexes: list[int], error: str, passport_id: str = "") -> None:
        for index in indexes:
            results.append(RowOutcome(index, STATUS_FAILED, "", synced_at, error, passport_id))

    states = store.current_students()
    passport_ids = store.taken_passport_ids()
    codes = store.taken_verification_codes()
    content_hashes = store.taken_content_hashes()
    created = 0
    groups, failures = _group_rows(raw_rows)
    for index, error in failures.items():
        fail([index], error)
    # The Skills tab is the admin-edited catalog, so it wins over text copied from award rows.
    catalog = {skill.id: skill for skill in _catalog_from_groups(groups)}
    catalog.update({skill.id: skill for skill in tab_catalog or []})
    store.upsert_skills(list(catalog.values()))
    synced: set[str] = set()
    for email, group in groups.items():
        skills = tuple(
            canonical_skills(
                [
                    Skill(
                        skill=fact.skill,
                        badge=fact.badge,
                        awarded_on=fact.awarded_on,
                        description=fact.description,
                        skill_id=fact.skill_id or None,
                    )
                    for fact in group.rows
                ]
            )
        )
        fingerprint = skill_fingerprint(skills)
        state = states.get(email)
        if state is None:
            if not group.full_name:
                fail(group.indexes, "missing_full_name")
                continue
            if group.passport_id and group.passport_id in passport_ids:
                fail(group.indexes, "passport_id_taken")
                continue
            if group.passport_id:
                passport_id = group.passport_id
                passport_ids.add(passport_id)
            else:
                passport_id = _mint(passport_ids, 10, _format_passport_id)
            holder = group.full_name
            version_number = 1
            store.insert_student(email, holder, passport_id)
            created += 1
        elif state.latest_fingerprint == fingerprint:
            passport_id = state.passport_id
            holder = state.holder_name
            version_number = state.latest_version
            if group.full_name and group.full_name != state.full_name:
                store.save_student_name(email, group.full_name)
        else:
            passport_id = state.passport_id
            holder = group.full_name or state.holder_name
            version_number = state.latest_version + 1
            if group.full_name and group.full_name != state.full_name:
                store.save_student_name(email, group.full_name)
            created += 1
        if state is None or state.latest_fingerprint != fingerprint:
            _insert_version(
                store,
                email=email,
                passport_id=passport_id,
                version_number=version_number,
                holder_name=holder,
                fingerprint=fingerprint,
                skills=skills,
                codes=codes,
                content_hashes=content_hashes,
            )
        for fact in group.rows:
            store.remember_source(
                _record_key(email, fact.skill, fact.badge, fact.raw_awarded_on),
                email,
            )
        synced.add(email)
        for index in group.indexes:
            results.append(
                RowOutcome(index, STATUS_SYNCED, f"V{version_number}", synced_at, "", passport_id)
            )
    emails = synced
    _fill_pending_pdfs(store, emails)
    _anchor_pending(store, emails, chain)
    return created


def _insert_version(
    store: SyncStore,
    *,
    email: str,
    passport_id: str,
    version_number: int,
    holder_name: str,
    fingerprint: str,
    skills: tuple[Skill, ...],
    codes: set[str],
    content_hashes: set[str],
) -> None:
    code = _mint(codes, 16, _format_code)
    document_hash = content_hash(
        holder_name=holder_name,
        passport_id=passport_id,
        skills=skills,
        version=version_number,
    )
    if document_hash in content_hashes:
        raise RuntimeError("content_hash_collision")
    content_hashes.add(document_hash)
    store.insert_version(
        VersionRecord(
            passport_id=passport_id,
            email=email,
            version_number=version_number,
            holder_name=holder_name,
            verification_code=code,
            verification_id_hash=verification_id_hash(code),
            skill_fingerprint=fingerprint,
            content_hash=document_hash,
            anchor_status="pending",
            pdf_en_path=None,
            pdf_ka_path=None,
            tx_hash=None,
            issued_at=_now(),
            skills=skills,
        )
    )


def _fill_pending_pdfs(store: SyncStore, emails: set[str]) -> None:
    storage = get_storage()
    for pending in store.pending_pdfs():
        if pending.email not in emails:
            continue
        en_path, ka_path = publish_pdfs(
            PassportPdf(
                holder_name=pending.holder_name,
                passport_id=pending.passport_id,
                version=pending.version_number,
                issued_on=pending.issued_at[:10],
                verification_code=pending.verification_code,
                skills=pending.skills,
            ),
            storage,
        )
        store.save_pdf_paths(pending.email, pending.version_number, en_path, ka_path)


def _anchor_pending(store: SyncStore, emails: set[str], chain: AnchorChain | None) -> None:
    # Every unconfirmed version is retried on each run, not only rows that changed,
    # so a failed anchor recovers on the next scheduled sync.
    del emails
    client = chain if chain is not None else chain_from_settings()
    if client is None:
        return
    now = _now()
    for pending in store.pending_anchors():
        try:
            publish_anchor(pending, client, now=now)
        except Exception:
            pending.anchor_status = "failed"
            pending.anchored_at = None
        store.save_anchor(
            pending.email,
            pending.version_number,
            status=pending.anchor_status,
            tx_hash=pending.tx_hash,
            anchored_at=pending.anchored_at,
        )


def _skill_row(skill: CatalogSkill, with_ka: bool) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": skill.id,
        "name": skill.name,
        "category": skill.category,
        "badge": skill.badge,
        "description": skill.description,
        "updated_at": _now(),
    }
    if with_ka:
        row["name_ka"] = skill.name_ka or ""
    return row


def _student_embed(value: object) -> dict[str, object] | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return None


def _catalog_from_groups(groups: dict[str, _EmailGroup]) -> list[CatalogSkill]:
    """Distinct catalog rows for facts that have a Skill ID. The last sheet row wins."""
    catalog: dict[str, CatalogSkill] = {}
    for group in groups.values():
        for fact in group.rows:
            if fact.skill_id:
                catalog[fact.skill_id] = CatalogSkill(
                    id=fact.skill_id,
                    name=fact.skill,
                    category=fact.category,
                    badge=fact.badge,
                    description=fact.description,
                )
    return list(catalog.values())


def _skills_from_rows(value: object) -> tuple[Skill, ...]:
    ordered = sorted(_nested_rows(value), key=lambda item: _as_int(item.get("position", 0)))
    return tuple(
        Skill(
            skill=str(item["skill"]),
            badge=str(item["badge"]),
            awarded_on=None if item.get("awarded_on") is None else str(item["awarded_on"]),
            description=str(item.get("description") or ""),
        )
        for item in ordered
    )


def _group_rows(
    raw_rows: list[dict[str, object]],
) -> tuple[dict[str, _EmailGroup], dict[int, str]]:
    groups: dict[str, _EmailGroup] = {}
    failures: dict[int, str] = {}
    for index, raw in enumerate(raw_rows):
        row = _normalize_row(raw)
        email = row["email"].lower()
        skill = row["skill"]
        if not email and not skill:
            # Blank line or a note below the data. Not a record.
            continue
        if not email:
            failures[index] = "missing_email"
            continue
        if not skill:
            failures[index] = "missing_skill"
            continue
        if not email_domain_allowed(email):
            failures[index] = "email_domain_not_allowed"
            continue
        fact = _SkillFact(
            skill=skill,
            badge=row["badge"],
            awarded_on=normalize_awarded_on(row["awarded_on"]),
            raw_awarded_on=row["awarded_on"],
            description=row["description"],
            skill_id=row["skill_id"].upper(),
            category=row["skill_category"],
        )
        group = groups.get(email)
        if group is None:
            groups[email] = _EmailGroup(
                full_name=row["full_name"],
                rows=[fact],
                indexes=[index],
                passport_id=row["passport_id"].upper(),
            )
            continue
        if row["full_name"]:
            group.full_name = row["full_name"]
        if row["passport_id"] and not group.passport_id:
            group.passport_id = row["passport_id"].upper()
        group.rows.append(fact)
        group.indexes.append(index)
    return groups, failures


def _normalize_row(row: dict[str, object]) -> dict[str, str]:
    found: dict[str, str] = {}
    for key, value in row.items():
        name = str(key).strip().lower()
        for field, names in _ALIASES.items():
            if name in names and field not in found:
                found[field] = _cell(value)
    normalized = {column: found.get(column, "") for column in _COLUMNS}
    if not normalized["full_name"]:
        parts = (found.get("first_name", ""), found.get("last_name", ""))
        normalized["full_name"] = " ".join(part for part in parts if part)
    badge = normalized["badge"]
    if badge.startswith("=") or (not badge and found.get("skill_category")):
        # Official sheet: badge is a formula of the category. Use the computed code.
        normalized["badge"] = _CATEGORY_BADGES.get(found.get("skill_category", "").lower(), "")
    return normalized


def _cell(value: object) -> str:
    if value is None:
        return ""
    return unicodedata.normalize("NFC", str(value).strip())


def _record_key(email: str, skill: str, badge: str, raw_awarded_on: str) -> str:
    payload = "\x1f".join((email, skill, badge, raw_awarded_on))
    return hashlib.sha256(payload.encode()).hexdigest()


def _mint(taken: set[str], length: int, format_raw: Callable[[str], str]) -> str:
    for _ in range(32):
        raw = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        candidate = format_raw(raw)
        if candidate not in taken:
            taken.add(candidate)
            return candidate
    raise RuntimeError("token_exhausted")


def _format_passport_id(raw: str) -> str:
    return f"BTU-{raw}"


def _format_code(raw: str) -> str:
    return f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _table_rows(data: object) -> list[dict[str, object]]:
    if not isinstance(data, list):
        return []
    return [cast(dict[str, object], row) for row in data if isinstance(row, dict)]


def _nested_rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [cast(dict[str, object], row) for row in value if isinstance(row, dict)]


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise RuntimeError("expected_integer")
    return int(value)
