import copy
import dataclasses
import hashlib
import json
import logging
import secrets
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast

import gspread
from postgrest.exceptions import APIError

from passport_api.anchoring import SNAPSHOT_MISMATCH, AnchorRecord, reconcile_anchors
from passport_api.chain import AnchorChain, chain_from_settings
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
_UNIQUE_VIOLATION = "23505"
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


# A sync takes about a minute. A run still "running" after this long was killed (for
# example by a deploy) and is released so it cannot block every later sync.
STALE_LOCK_AFTER = timedelta(minutes=10)
STALE_LOCK_ERROR = "stale_lock"
# Versions the reconciler still works on. "failed" is the legacy name for "retrying".
OPEN_ANCHOR = ("pending", "retrying", "failed")
ANCHOR_LOCK_NAME = "reconciler"
STUDENT_ARCHIVED = "student_archived"
# Row error codes for a unit the database refused. See supabase/migrations/0011_atomic_sync.sql.
SYNC_STALE = "sync_stale"
_UNIT_STALE = "PS001"
_UNIT_ARCHIVED = "PS002"
_UNIT_MALFORMED = "PS003"

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
    archived: bool = False


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
    # Anchoring bookkeeping (migration 0010). See passport_api.anchoring.
    anchor_nonce: int | None = None
    anchor_gas_price: int | None = None
    anchor_submitted_at: str | None = None
    anchor_attempts: int = 0
    anchor_last_error: str | None = None
    anchor_next_attempt_at: str | None = None
    anchor_tx_hashes: list[str] = dataclasses.field(default_factory=list)
    # Set when rows read from the database do not hash to the stored hashes (see
    # snapshot_problem). The reconciler never sends such a version to the chain.
    snapshot_error: str | None = None


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
    started_at: datetime = dataclasses.field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class StudentState:
    email: str
    full_name: str
    passport_id: str
    latest_version: int
    latest_fingerprint: str
    holder_name: str
    # Archived students are listed so sync and awards can say so, but never get new versions.
    archived: bool = False


@dataclass(frozen=True)
class StudentUnit:
    """Everything one student's sync writes. The store commits it all or none of it.

    `version` is None when the sheet matches the stored latest version: the unit then only
    renames the student (when `rename`) and remembers the source rows.
    """

    email: str
    passport_id: str
    full_name: str
    rename: bool
    # Latest stored version number the unit was built on (0: none). A stale unit is refused.
    expected_latest: int
    version: VersionRecord | None
    source_keys: tuple[str, ...]


@dataclass(frozen=True)
class UnitResult:
    """What the store reports back after committing a unit: the rows as stored."""

    passport_id: str
    version_number: int | None
    holder_name: str | None
    created_student: bool
    created_version: bool
    # The stored skill snapshot of the version, in stored order. None when the unit had no version.
    skills: tuple[Skill, ...] | None


class SnapshotMismatchError(RuntimeError):
    """The stored version does not hash to what was submitted. Never expected; never anchored."""


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

    def abort(self, error: str = "sheet_unavailable") -> None: ...

    def finish(self, rows_read: int, versions_created: int) -> None: ...

    def current_students(self) -> dict[str, StudentState]: ...

    def commit_student_unit(self, unit: StudentUnit) -> UnitResult:
        """Write the student, the new version with its skills and the source rows in ONE
        transaction. Retrying a unit that already committed changes nothing."""
        ...

    def upsert_skills(self, skills: list[CatalogSkill]) -> None: ...

    def taken_passport_ids(self) -> set[str]: ...

    def taken_verification_codes(self) -> set[str]: ...

    def taken_content_hashes(self) -> set[str]: ...

    def pending_pdfs(self) -> list[PendingPdf]: ...

    def save_pdf_paths(
        self, email: str, version_number: int, en_path: str, ka_path: str
    ) -> None: ...

    def pending_anchors(self) -> list[VersionRecord]: ...

    def save_anchor(self, email: str, version_number: int, record: AnchorRecord) -> None: ...

    def try_lock_anchors(self, now: datetime, until: datetime) -> bool: ...

    def unlock_anchors(self) -> None: ...


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
        self._anchor_lock_until: datetime | None = None

    def has_running(self) -> bool:
        return any(run.status == "running" for run in self.runs)

    def try_acquire(self) -> bool:
        cutoff = datetime.now(UTC) - STALE_LOCK_AFTER
        for run in self.runs:
            if run.status == "running" and run.started_at < cutoff:
                run.status = "failed"
                run.error = STALE_LOCK_ERROR
        if self.has_running():
            return False
        self.runs.append(RunRecord(status="running", rows_read=0, versions_created=0, error=None))
        return True

    def record_skipped(self) -> None:
        self.runs.append(RunRecord(status="skipped", rows_read=0, versions_created=0, error=None))

    def abort(self, error: str = "sheet_unavailable") -> None:
        self._close("failed", 0, 0, error)

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
                # No version yet: an archived student stays refused, an active one is healed
                # by the next unit (it gets version 1).
                states[student.email] = _without_versions(student)
                continue
            states[student.email] = StudentState(
                email=student.email,
                full_name=student.full_name,
                passport_id=student.passport_id,
                latest_version=latest_version.version_number,
                latest_fingerprint=latest_version.skill_fingerprint,
                holder_name=latest_version.holder_name,
                archived=student.archived,
            )
        return states

    def insert_student(self, email: str, full_name: str, passport_id: str) -> None:
        """Seed a bare student row (the shape of old admin-managed rows). Tests only."""
        if any(student.email == email for student in self.students):
            raise APIError({"code": _UNIQUE_VIOLATION, "message": "students_email_key"})
        self.students.append(
            StudentRecord(email=email, full_name=full_name, passport_id=passport_id)
        )

    def commit_student_unit(self, unit: StudentUnit) -> UnitResult:
        """Same rules as the sync_student_unit SQL function: all of the unit or none of it."""
        before = (
            copy.deepcopy(self.students),
            list(self.versions),
            dict(self._sources),
        )
        try:
            return self._apply_unit(unit)
        except BaseException:
            self.students, self.versions, self._sources = before
            raise

    def _apply_unit(self, unit: StudentUnit) -> UnitResult:
        student = next((s for s in self.students if s.email == unit.email), None)
        version = unit.version
        created_student = False
        if student is None:
            if version is None or unit.expected_latest != 0:
                raise _unit_error(_UNIT_STALE, "sync_unit_stale")
            if any(other.passport_id == unit.passport_id for other in self.students):
                raise APIError({"code": _UNIQUE_VIOLATION, "message": "students_passport_id_key"})
            student = StudentRecord(
                email=unit.email, full_name=unit.full_name, passport_id=unit.passport_id
            )
            self.students.append(student)
            created_student = True
        else:
            if student.archived:
                raise _unit_error(_UNIT_ARCHIVED, "sync_unit_archived")
            if student.passport_id != unit.passport_id:
                raise _unit_error(_UNIT_STALE, "sync_unit_stale")
            if unit.rename:
                student.full_name = unit.full_name
        owned = [v for v in self.versions if v.email == unit.email]
        latest = max(owned, key=lambda v: v.version_number, default=None)
        created_version = False
        if version is not None:
            if not version.skills:
                raise _unit_error(_UNIT_MALFORMED, "sync_unit_malformed")
            if latest is not None and latest.skill_fingerprint == version.skill_fingerprint:
                if (
                    latest.version_number != version.version_number
                    or latest.content_hash != version.content_hash
                ):
                    raise _unit_error(_UNIT_STALE, "sync_unit_stale")
            else:
                if (latest.version_number if latest else 0) != unit.expected_latest:
                    raise _unit_error(_UNIT_STALE, "sync_unit_stale")
                if version.version_number != unit.expected_latest + 1:
                    raise _unit_error(_UNIT_MALFORMED, "sync_unit_malformed")
                for skill in version.skills:
                    if skill.skill_id is not None and skill.skill_id not in self.skills:
                        raise RuntimeError("skill_not_in_catalog")
                # The stored copy is its own object, as a database row would be.
                latest = dataclasses.replace(
                    version,
                    skills=tuple(version.skills),
                    anchor_tx_hashes=list(version.anchor_tx_hashes),
                )
                self.versions.append(latest)
                created_version = True
        self._remember_sources(unit)
        return UnitResult(
            passport_id=student.passport_id,
            version_number=None if latest is None else latest.version_number,
            holder_name=None if latest is None else latest.holder_name,
            created_student=created_student,
            created_version=created_version,
            skills=latest.skills if version is not None and latest is not None else None,
        )

    def _remember_sources(self, unit: StudentUnit) -> None:
        for key in unit.source_keys:
            self._sources.setdefault(key, unit.email)

    def upsert_skills(self, skills: list[CatalogSkill]) -> None:
        for skill in skills:
            self.skills[skill.id] = skill

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
        return [version for version in self.versions if version.anchor_status in OPEN_ANCHOR]

    def save_anchor(self, email: str, version_number: int, record: AnchorRecord) -> None:
        for version in self.versions:
            if version.email == email and version.version_number == version_number:
                if version is not record:
                    _copy_anchor_fields(record, version)
                return
        raise RuntimeError("version_missing")

    def try_lock_anchors(self, now: datetime, until: datetime) -> bool:
        if self._anchor_lock_until is not None and self._anchor_lock_until > now:
            return False
        self._anchor_lock_until = until
        return True

    def unlock_anchors(self) -> None:
        self._anchor_lock_until = None

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

    def _release_stale_runs(self) -> None:
        cutoff = (datetime.now(UTC) - STALE_LOCK_AFTER).isoformat()
        get_supabase().table("sync_runs").update(
            {"status": "failed", "error": STALE_LOCK_ERROR, "finished_at": _now()}
        ).eq("status", "running").lt("started_at", cutoff).execute()

    def try_acquire(self) -> bool:
        self._release_stale_runs()
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

    def abort(self, error: str = "sheet_unavailable") -> None:
        self._update_running("failed", 0, 0, error)

    def finish(self, rows_read: int, versions_created: int) -> None:
        self._update_running("completed", rows_read, versions_created, None)

    def current_students(self) -> dict[str, StudentState]:
        response = (
            get_supabase()
            .table("students")
            .select(
                "email, full_name, passport_id, deleted_at, "
                "passport_versions(version_number, skill_fingerprint, holder_name)"
            )
            .execute()
        )
        states: dict[str, StudentState] = {}
        for row in _table_rows(response.data):
            archived = row.get("deleted_at") is not None
            versions = _nested_rows(row.get("passport_versions"))
            if not versions:
                # No version yet: an archived student stays refused, an active one is healed
                # by the next unit (it gets version 1) instead of failing with a conflict.
                states[str(row["email"])] = StudentState(
                    email=str(row["email"]),
                    full_name=str(row["full_name"]),
                    passport_id=str(row["passport_id"]),
                    latest_version=0,
                    latest_fingerprint="",
                    holder_name=str(row["full_name"]),
                    archived=archived,
                )
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
                archived=archived,
            )
        return states

    def commit_student_unit(self, unit: StudentUnit) -> UnitResult:
        # One RPC is one Postgres transaction: the function either stores the student, the
        # version, its skills and the source rows, or none of them.
        response = (
            get_supabase().rpc("sync_student_unit", {"p_unit": _unit_payload(unit)}).execute()
        )
        return _unit_result(response.data)

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
            .select(_ANCHOR_SELECT)
            .in_("anchor_status", list(OPEN_ANCHOR))
            .order("issued_at")
            .execute()
        )
        records: list[VersionRecord] = []
        for row in _table_rows(response.data):
            record = _anchor_record(row)
            if record is not None:
                records.append(record)
        return records

    def version_by_id(self, version_id: str) -> VersionRecord | None:
        response = (
            get_supabase()
            .table("passport_versions")
            .select(_ANCHOR_SELECT)
            .eq("id", version_id)
            .limit(1)
            .execute()
        )
        rows = _table_rows(response.data)
        return _anchor_record(rows[0]) if rows else None

    def save_anchor(self, email: str, version_number: int, record: AnchorRecord) -> None:
        student_id = self._student_id(email)
        (
            get_supabase()
            .table("passport_versions")
            .update(
                {
                    "anchor_status": record.anchor_status,
                    "tx_hash": record.tx_hash,
                    "anchored_at": record.anchored_at,
                    "anchor_nonce": record.anchor_nonce,
                    "anchor_gas_price": record.anchor_gas_price,
                    "anchor_submitted_at": record.anchor_submitted_at,
                    "anchor_attempts": record.anchor_attempts,
                    "anchor_last_error": record.anchor_last_error,
                    "anchor_next_attempt_at": record.anchor_next_attempt_at,
                    "anchor_tx_hashes": list(record.anchor_tx_hashes),
                }
            )
            .eq("student_id", student_id)
            .eq("version_number", version_number)
            .execute()
        )

    def try_lock_anchors(self, now: datetime, until: datetime) -> bool:
        # One conditional UPDATE is atomic: of two runs, only one sees a row come back.
        response = (
            get_supabase()
            .table("anchor_reconcile_lock")
            .update({"locked_until": until.isoformat()})
            .eq("name", ANCHOR_LOCK_NAME)
            .lt("locked_until", now.isoformat())
            .execute()
        )
        return bool(_table_rows(response.data))

    def unlock_anchors(self) -> None:
        (
            get_supabase()
            .table("anchor_reconcile_lock")
            .update({"locked_until": "1970-01-01T00:00:00+00:00"})
            .eq("name", ANCHOR_LOCK_NAME)
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
        store.abort("sync_failed")
        raise
    try:
        store.finish(len(raw_rows), created)
    except Exception:
        # Do not leave the run "running": that would block every later sync.
        _log.exception("sync_finish_failed")
        try:
            store.abort("sync_finish_failed")
        except Exception:
            _log.exception("sync_abort_failed")
        raise
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

    def process(email: str, group: _EmailGroup) -> None:
        nonlocal created
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
        if state is not None and state.archived:
            # An archived student is revoked. Restore them in the admin panel first.
            fail(group.indexes, STUDENT_ARCHIVED, state.passport_id)
            return
        if state is None:
            if not group.full_name:
                fail(group.indexes, "missing_full_name")
                return
            if group.passport_id and group.passport_id in passport_ids:
                fail(group.indexes, "passport_id_taken")
                return
            if group.passport_id:
                passport_id = group.passport_id
                passport_ids.add(passport_id)
            else:
                passport_id = _mint(passport_ids, 10, _format_passport_id)
            student_name = group.full_name
            rename = False
            holder = group.full_name
            expected_latest = 0
            changed = True
        else:
            # Includes a student with no version yet: its fingerprint is empty, so it gets
            # version 1 here instead of failing as a conflict on every run.
            passport_id = state.passport_id
            rename = bool(group.full_name) and group.full_name != state.full_name
            student_name = group.full_name if rename else state.full_name
            expected_latest = state.latest_version
            changed = state.latest_fingerprint != fingerprint
            holder = (group.full_name or state.holder_name) if changed else state.holder_name
        version_number = expected_latest + 1 if changed else expected_latest
        unit = StudentUnit(
            email=email,
            passport_id=passport_id,
            full_name=student_name,
            rename=rename,
            expected_latest=expected_latest,
            version=(
                _build_version(
                    email=email,
                    passport_id=passport_id,
                    version_number=version_number,
                    holder_name=holder,
                    fingerprint=fingerprint,
                    skills=skills,
                    codes=codes,
                    content_hashes=content_hashes,
                )
                if changed
                else None
            ),
            source_keys=tuple(
                _record_key(email, fact.skill, fact.badge, fact.raw_awarded_on)
                for fact in group.rows
            ),
        )
        # The whole unit commits at once. Anchoring and the Sheet write-back come after.
        result = store.commit_student_unit(unit)
        _check_snapshot(unit, result)
        if result.created_version:
            created += 1
        synced.add(email)
        for index in group.indexes:
            results.append(
                RowOutcome(index, STATUS_SYNCED, f"V{version_number}", synced_at, "", passport_id)
            )

    for email, group in groups.items():
        created_before = created
        try:
            process(email, group)
        except Exception as exc:
            # One student must not stop the run. Mark their rows and carry on.
            _log.exception("student_sync_failed")
            created = created_before
            fail(group.indexes, _failure_code(exc))
    emails = synced
    _fill_pending_pdfs(store, emails)
    _anchor_pending(store, emails, chain)
    return created


def _without_versions(student: StudentRecord) -> StudentState:
    return StudentState(
        email=student.email,
        full_name=student.full_name,
        passport_id=student.passport_id,
        latest_version=0,
        latest_fingerprint="",
        holder_name=student.full_name,
        archived=student.archived,
    )


def _failure_code(exc: Exception) -> str:
    """Row error code for an unexpected failure. Never includes internal details."""
    if isinstance(exc, SnapshotMismatchError):
        return SNAPSHOT_MISMATCH
    if isinstance(exc, APIError):
        if exc.code == _UNIQUE_VIOLATION:
            return "student_conflict"
        if exc.code == _UNIT_STALE:
            return SYNC_STALE
        if exc.code == _UNIT_ARCHIVED:
            return STUDENT_ARCHIVED
    return "sync_error"


def _build_version(
    *,
    email: str,
    passport_id: str,
    version_number: int,
    holder_name: str,
    fingerprint: str,
    skills: tuple[Skill, ...],
    codes: set[str],
    content_hashes: set[str],
) -> VersionRecord:
    """The new version, hashed from exactly the skills that will be stored with it."""
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
    return VersionRecord(
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


def snapshot_problem(
    *,
    holder_name: str,
    passport_id: str,
    version_number: int,
    skills: tuple[Skill, ...],
    skill_fingerprint_value: str,
    content_hash_value: str,
) -> str | None:
    """Why stored content does not hash to the stored hashes, or None when it does."""
    if not skills:
        return "no_skills"
    if skill_fingerprint(skills) != skill_fingerprint_value:
        return "skill_fingerprint_mismatch"
    expected = content_hash(
        holder_name=holder_name, passport_id=passport_id, skills=skills, version=version_number
    )
    if expected != content_hash_value:
        return "content_hash_mismatch"
    return None


def _check_snapshot(unit: StudentUnit, result: UnitResult) -> None:
    """After the commit: the stored version must hash to what was submitted.

    The hash was computed from the skills sent in the unit and the store wrote exactly those
    in the same transaction. Reading them back and hashing again proves it. A failure here is
    never expected; the version is then reported to the Sheet and the anchoring guard refuses
    to anchor it.
    """
    version = unit.version
    if version is None:
        return
    stored = result.skills
    if (
        stored is None
        or result.version_number != version.version_number
        or result.holder_name != version.holder_name
        or result.passport_id != unit.passport_id
        or snapshot_problem(
            holder_name=version.holder_name,
            passport_id=unit.passport_id,
            version_number=version.version_number,
            skills=stored,
            skill_fingerprint_value=version.skill_fingerprint,
            content_hash_value=version.content_hash,
        )
        is not None
    ):
        raise SnapshotMismatchError(f"{unit.email} v{version.version_number}")


def _unit_error(code: str, message: str) -> APIError:
    """The error a failed sync_student_unit call raises, as PostgREST reports it."""
    return APIError({"code": code, "message": message})


def _unit_payload(unit: StudentUnit) -> dict[str, Any]:
    version = unit.version
    return {
        "email": unit.email,
        "passport_id": unit.passport_id,
        "full_name": unit.full_name,
        "rename": unit.rename,
        "expected_latest": unit.expected_latest,
        "source_keys": list(unit.source_keys),
        "version": None
        if version is None
        else {
            "version_number": version.version_number,
            "holder_name": version.holder_name,
            "verification_code": version.verification_code,
            "verification_id_hash": version.verification_id_hash,
            "skill_fingerprint": version.skill_fingerprint,
            "content_hash": version.content_hash,
            "issued_at": version.issued_at,
            "skills": [
                {
                    "skill": skill.skill,
                    "badge": skill.badge,
                    "awarded_on": skill.awarded_on,
                    "description": skill.description,
                    "skill_id": skill.skill_id,
                }
                for skill in version.skills
            ],
        },
    }


def _unit_result(data: object) -> UnitResult:
    if not isinstance(data, dict):
        raise RuntimeError("sync_unit_no_result")
    row = cast(dict[str, object], data)
    stored = row.get("skills")
    number = row.get("version_number")
    holder = row.get("holder_name")
    return UnitResult(
        passport_id=str(row["passport_id"]),
        version_number=None if number is None else _as_int(number),
        holder_name=None if holder is None else str(holder),
        created_student=bool(row.get("created_student")),
        created_version=bool(row.get("created_version")),
        skills=None if stored is None else _skills_from_stored(stored),
    )


def _skills_from_stored(value: object) -> tuple[Skill, ...]:
    """Skills as returned by the unit function: already in stored (position) order."""
    return tuple(
        Skill(
            skill=str(item["skill"]),
            badge=str(item["badge"]),
            awarded_on=None if item.get("awarded_on") is None else str(item["awarded_on"]),
            description=str(item.get("description") or ""),
            skill_id=None if item.get("skill_id") is None else str(item["skill_id"]),
        )
        for item in _nested_rows(value)
    )


def _fill_pending_pdfs(store: SyncStore, emails: set[str]) -> None:
    storage = get_storage()
    for pending in store.pending_pdfs():
        if pending.email not in emails:
            continue
        try:
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
        except Exception:
            # The PDF stays pending and is retried on the next run.
            _log.warning("pdf_publish_failed", exc_info=True)


_ANCHOR_SELECT = (
    "id, version_number, holder_name, verification_code, verification_id_hash, "
    "skill_fingerprint, content_hash, anchor_status, tx_hash, anchored_at, issued_at, "
    "anchor_nonce, anchor_gas_price, anchor_submitted_at, anchor_attempts, anchor_last_error, "
    "anchor_next_attempt_at, anchor_tx_hashes, "
    "skill_entries(skill, badge, awarded_on, description, position), "
    "students(email, passport_id)"
)


def _anchor_record(row: dict[str, Any]) -> VersionRecord | None:
    student = _student_embed(row.get("students"))
    if student is None:
        return None
    issued_at = row.get("issued_at")
    hashes = row.get("anchor_tx_hashes")
    skills = _skills_from_rows(row.get("skill_entries"))
    return VersionRecord(
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
        tx_hash=_opt_str(row.get("tx_hash")),
        issued_at=_now() if issued_at is None else str(issued_at),
        skills=skills,
        anchored_at=_opt_str(row.get("anchored_at")),
        anchor_nonce=_opt_int(row.get("anchor_nonce")),
        anchor_gas_price=_opt_int(row.get("anchor_gas_price")),
        anchor_submitted_at=_opt_str(row.get("anchor_submitted_at")),
        anchor_attempts=_opt_int(row.get("anchor_attempts")) or 0,
        anchor_last_error=_opt_str(row.get("anchor_last_error")),
        anchor_next_attempt_at=_opt_str(row.get("anchor_next_attempt_at")),
        anchor_tx_hashes=[str(h) for h in hashes] if isinstance(hashes, list) else [],
        snapshot_error=snapshot_problem(
            holder_name=str(row["holder_name"]),
            passport_id=str(student["passport_id"]),
            version_number=_as_int(row["version_number"]),
            skills=skills,
            skill_fingerprint_value=str(row["skill_fingerprint"]),
            content_hash_value=str(row["content_hash"]),
        ),
    )


def _opt_str(value: object) -> str | None:
    return None if value is None else str(value)


def _opt_int(value: object) -> int | None:
    return None if value is None else _as_int(value)


def _copy_anchor_fields(source: AnchorRecord, target: VersionRecord) -> None:
    target.anchor_status = source.anchor_status
    target.tx_hash = source.tx_hash
    target.anchored_at = source.anchored_at
    target.anchor_nonce = source.anchor_nonce
    target.anchor_gas_price = source.anchor_gas_price
    target.anchor_submitted_at = source.anchor_submitted_at
    target.anchor_attempts = source.anchor_attempts
    target.anchor_last_error = source.anchor_last_error
    target.anchor_next_attempt_at = source.anchor_next_attempt_at
    target.anchor_tx_hashes = list(source.anchor_tx_hashes)


def _anchor_pending(store: SyncStore, emails: set[str], chain: AnchorChain | None) -> None:
    # Every unconfirmed version is looked at on each run, not only rows that changed, so a
    # dropped or stuck transaction recovers on the next scheduled sync. A broken chain never
    # fails the sync: the ledger is already saved and the reconciler runs again later.
    del emails
    client = chain if chain is not None else chain_from_settings()
    if client is None:
        return
    try:
        reconcile_anchors(store, client)
    except Exception:
        _log.exception("anchor_reconcile_failed")


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
