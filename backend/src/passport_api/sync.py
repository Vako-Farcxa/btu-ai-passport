import hashlib
import json
import secrets
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast

import gspread
from gspread.auth import READONLY_SCOPES
from postgrest.exceptions import APIError

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
from passport_api.settings import settings

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_COLUMNS = ("email", "full_name", "skill", "badge", "awarded_on")


class SheetUnavailableError(Exception):
    pass


class Sheet(Protocol):
    def read_rows(self) -> list[dict[str, object]]: ...


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


@dataclass
class _EmailGroup:
    full_name: str
    rows: list[_SkillFact]


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

    def remember_source(self, record_key: str, email: str) -> None: ...

    def taken_passport_ids(self) -> set[str]: ...

    def taken_verification_codes(self) -> set[str]: ...

    def taken_content_hashes(self) -> set[str]: ...

    def pending_pdfs(self) -> list[PendingPdf]: ...

    def save_pdf_paths(
        self, email: str, version_number: int, en_path: str, ka_path: str
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

    def read_rows(self) -> list[dict[str, object]]:
        self.reads += 1
        if self._error is not None:
            raise self._error
        return [dict(row) for row in self._rows]


class GspreadSheet:
    def read_rows(self) -> list[dict[str, object]]:
        if not settings.sheet_id or not settings.google_service_account_json:
            raise SheetUnavailableError("sheet_not_configured")
        try:
            parsed = json.loads(settings.google_service_account_json)
        except json.JSONDecodeError as exc:
            raise SheetUnavailableError("sheet_not_configured") from exc
        if not isinstance(parsed, dict):
            raise SheetUnavailableError("sheet_not_configured")
        info = cast(dict[str, Any], parsed)
        try:
            client = gspread.service_account_from_dict(info, scopes=READONLY_SCOPES)
            worksheet = client.open_by_key(settings.sheet_id).get_worksheet(0)
            records = worksheet.get_all_records(default_blank="")
        except SheetUnavailableError:
            raise
        except Exception as exc:
            raise SheetUnavailableError("sheet_unavailable") from exc
        return [dict(record) for record in records]


class MemorySyncStore:
    def __init__(self) -> None:
        self.students: list[StudentRecord] = []
        self.versions: list[VersionRecord] = []
        self.runs: list[RunRecord] = []
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
        self.versions.append(version)

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
                "position": position,
            }
            for position, skill in enumerate(version.skills, start=1)
        ]
        if skill_rows:
            get_supabase().table("skill_entries").insert(skill_rows).execute()

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
                "skill_entries(skill, badge, awarded_on, position), "
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


def run_sync(store: SyncStore, sheet: Sheet) -> SyncResult:
    if not store.try_acquire():
        store.record_skipped()
        return SyncResult(status="skipped", rows_read=0, versions_created=0, error=None)
    try:
        raw_rows = sheet.read_rows()
    except Exception:
        store.abort()
        return SyncResult(
            status="failed", rows_read=0, versions_created=0, error="sheet_unavailable"
        )
    created = _issue_versions(store, raw_rows)
    store.finish(len(raw_rows), created)
    return SyncResult(
        status="completed", rows_read=len(raw_rows), versions_created=created, error=None
    )


def _issue_versions(store: SyncStore, raw_rows: list[dict[str, object]]) -> int:
    states = store.current_students()
    passport_ids = store.taken_passport_ids()
    codes = store.taken_verification_codes()
    content_hashes = store.taken_content_hashes()
    created = 0
    groups = _group_rows(raw_rows)
    for email, group in groups.items():
        skills = tuple(
            canonical_skills(
                [
                    Skill(skill=fact.skill, badge=fact.badge, awarded_on=fact.awarded_on)
                    for fact in group.rows
                ]
            )
        )
        fingerprint = skill_fingerprint(skills)
        state = states.get(email)
        if state is None:
            if not group.full_name:
                continue
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
    _fill_pending_pdfs(store, set(groups))
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


def _student_embed(value: object) -> dict[str, object] | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return None


def _skills_from_rows(value: object) -> tuple[Skill, ...]:
    ordered = sorted(_nested_rows(value), key=lambda item: _as_int(item.get("position", 0)))
    return tuple(
        Skill(
            skill=str(item["skill"]),
            badge=str(item["badge"]),
            awarded_on=None if item.get("awarded_on") is None else str(item["awarded_on"]),
        )
        for item in ordered
    )


def _group_rows(raw_rows: list[dict[str, object]]) -> dict[str, _EmailGroup]:
    groups: dict[str, _EmailGroup] = {}
    for raw in raw_rows:
        row = _normalize_row(raw)
        email = row["email"].lower()
        skill = row["skill"]
        if not email or not skill or not email.endswith("@btu.edu.ge"):
            continue
        fact = _SkillFact(
            skill=skill,
            badge=row["badge"],
            awarded_on=normalize_awarded_on(row["awarded_on"]),
            raw_awarded_on=row["awarded_on"],
        )
        group = groups.get(email)
        if group is None:
            groups[email] = _EmailGroup(full_name=row["full_name"], rows=[fact])
            continue
        if row["full_name"]:
            group.full_name = row["full_name"]
        group.rows.append(fact)
    return groups


def _normalize_row(row: dict[str, object]) -> dict[str, str]:
    normalized = dict.fromkeys(_COLUMNS, "")
    for key, value in row.items():
        name = str(key).strip().lower()
        if name in normalized:
            normalized[name] = _cell(value)
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
