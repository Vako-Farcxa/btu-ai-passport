"""Student flags: storage and the pure rules around them.

A flag is a short report from a student about one version of their own passport. It never
touches the passport, its hashes or its anchor. Two stores share one interface: memory
for demos and tests, and Supabase when credentials are set.
"""

import unicodedata
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol, cast

from postgrest.exceptions import APIError as PostgrestError

from passport_api.db import get_supabase
from passport_api.errors import APIError
from passport_api.schemas import FlagStatus
from passport_api.settings import settings

COMMENT_MIN = 10
COMMENT_MAX = 500
NOTE_MAX = 500
RATE_LIMIT = 5
RATE_WINDOW = timedelta(hours=1)
_UNIQUE_VIOLATION = "23505"


@dataclass(frozen=True)
class FlagRecord:
    id: str
    passport_id: str
    version: int
    verification_code: str
    student_email: str
    comment: str
    status: FlagStatus
    admin_note: str
    resolved_by: str | None
    created_at: str
    resolved_at: str | None
    student_seen_at: str | None

    @property
    def unread(self) -> bool:
        """An admin reply the student has not opened."""
        return self.status != "open" and self.student_seen_at is None


class FlagStore(Protocol):
    def create(
        self,
        *,
        passport_id: str,
        version: int,
        verification_code: str,
        student_email: str,
        comment: str,
    ) -> FlagRecord:
        """Insert an open flag. Raises APIError(409) when the version already has one."""
        ...

    def has_open(self, passport_id: str, version: int) -> bool: ...

    def count_since(self, student_email: str, since: datetime) -> int: ...

    def for_student(self, student_email: str) -> list[FlagRecord]: ...

    def mark_seen(self, student_email: str, when: datetime) -> None: ...

    def listing(self, status: FlagStatus | None) -> list[FlagRecord]: ...

    def open_count(self) -> int: ...

    def get(self, flag_id: str) -> FlagRecord | None: ...

    def close(
        self,
        flag_id: str,
        *,
        status: Literal["resolved", "dismissed"],
        admin_note: str,
        admin_email: str,
        when: datetime,
    ) -> FlagRecord | None: ...


def clean_comment(value: str) -> str:
    """NFC, trimmed. Line breaks and inner spacing are kept."""
    return unicodedata.normalize("NFC", value).strip()


def comment_valid(comment: str) -> bool:
    return COMMENT_MIN <= len(comment) <= COMMENT_MAX


def note_valid(note: str) -> bool:
    return len(note) <= NOTE_MAX


class MemoryFlagStore:
    def __init__(self) -> None:
        self._flags: list[FlagRecord] = []

    def create(
        self,
        *,
        passport_id: str,
        version: int,
        verification_code: str,
        student_email: str,
        comment: str,
    ) -> FlagRecord:
        if self.has_open(passport_id, version):
            raise APIError(409, "flag_already_open")
        record = FlagRecord(
            id=str(uuid.uuid4()),
            passport_id=passport_id,
            version=version,
            verification_code=verification_code,
            student_email=student_email,
            comment=comment,
            status="open",
            admin_note="",
            resolved_by=None,
            created_at=datetime.now(UTC).isoformat(),
            resolved_at=None,
            student_seen_at=None,
        )
        self._flags.append(record)
        return record

    def has_open(self, passport_id: str, version: int) -> bool:
        return any(
            flag.passport_id == passport_id and flag.version == version and flag.status == "open"
            for flag in self._flags
        )

    def count_since(self, student_email: str, since: datetime) -> int:
        return sum(
            1
            for flag in self._flags
            if flag.student_email == student_email
            and datetime.fromisoformat(flag.created_at) >= since
        )

    def for_student(self, student_email: str) -> list[FlagRecord]:
        own = [flag for flag in self._flags if flag.student_email == student_email]
        return sorted(own, key=lambda flag: flag.created_at, reverse=True)

    def mark_seen(self, student_email: str, when: datetime) -> None:
        self._flags = [
            replace(flag, student_seen_at=when.isoformat())
            if flag.student_email == student_email and flag.unread
            else flag
            for flag in self._flags
        ]

    def listing(self, status: FlagStatus | None) -> list[FlagRecord]:
        chosen = [flag for flag in self._flags if status is None or flag.status == status]
        return sorted(chosen, key=lambda flag: flag.created_at, reverse=True)

    def open_count(self) -> int:
        return sum(1 for flag in self._flags if flag.status == "open")

    def get(self, flag_id: str) -> FlagRecord | None:
        return next((flag for flag in self._flags if flag.id == flag_id), None)

    def close(
        self,
        flag_id: str,
        *,
        status: Literal["resolved", "dismissed"],
        admin_note: str,
        admin_email: str,
        when: datetime,
    ) -> FlagRecord | None:
        for index, flag in enumerate(self._flags):
            if flag.id == flag_id:
                updated = replace(
                    flag,
                    status=status,
                    admin_note=admin_note,
                    resolved_by=admin_email,
                    resolved_at=when.isoformat(),
                    student_seen_at=None,
                )
                self._flags[index] = updated
                return updated
        return None


_COLUMNS = (
    "id, passport_id, version, verification_code, student_email, comment, status, "
    "admin_note, resolved_by, created_at, resolved_at, student_seen_at"
)


def _record(row: dict[str, object]) -> FlagRecord:
    resolved_by = row.get("resolved_by")
    resolved_at = row.get("resolved_at")
    seen = row.get("student_seen_at")
    return FlagRecord(
        id=str(row["id"]),
        passport_id=str(row["passport_id"]),
        version=int(cast(int, row["version"])),
        verification_code=str(row["verification_code"]),
        student_email=str(row["student_email"]),
        comment=str(row["comment"]),
        status=cast(FlagStatus, str(row["status"])),
        admin_note=str(row.get("admin_note") or ""),
        resolved_by=None if resolved_by is None else str(resolved_by),
        created_at=str(row["created_at"]),
        resolved_at=None if resolved_at is None else str(resolved_at),
        student_seen_at=None if seen is None else str(seen),
    )


def _rows(data: object) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], data) if isinstance(data, list) else []


class SupabaseFlagStore:
    def create(
        self,
        *,
        passport_id: str,
        version: int,
        verification_code: str,
        student_email: str,
        comment: str,
    ) -> FlagRecord:
        try:
            response = (
                get_supabase()
                .table("flags")
                .insert(
                    {
                        "passport_id": passport_id,
                        "version": version,
                        "verification_code": verification_code,
                        "student_email": student_email,
                        "comment": comment,
                    }
                )
                .execute()
            )
        except PostgrestError as exc:
            if str(getattr(exc, "code", "")) == _UNIQUE_VIOLATION:
                raise APIError(409, "flag_already_open") from exc
            raise
        return _record(_rows(response.data)[0])

    def has_open(self, passport_id: str, version: int) -> bool:
        response = (
            get_supabase()
            .table("flags")
            .select("id")
            .eq("passport_id", passport_id)
            .eq("version", version)
            .eq("status", "open")
            .limit(1)
            .execute()
        )
        return bool(_rows(response.data))

    def count_since(self, student_email: str, since: datetime) -> int:
        response = (
            get_supabase()
            .table("flags")
            .select("id")
            .eq("student_email", student_email)
            .gte("created_at", since.isoformat())
            .execute()
        )
        return len(_rows(response.data))

    def for_student(self, student_email: str) -> list[FlagRecord]:
        response = (
            get_supabase()
            .table("flags")
            .select(_COLUMNS)
            .eq("student_email", student_email)
            .order("created_at", desc=True)
            .execute()
        )
        return [_record(row) for row in _rows(response.data)]

    def mark_seen(self, student_email: str, when: datetime) -> None:
        (
            get_supabase()
            .table("flags")
            .update({"student_seen_at": when.isoformat()})
            .eq("student_email", student_email)
            .neq("status", "open")
            .is_("student_seen_at", "null")
            .execute()
        )

    def listing(self, status: FlagStatus | None) -> list[FlagRecord]:
        query = get_supabase().table("flags").select(_COLUMNS)
        if status is not None:
            query = query.eq("status", status)
        response = query.order("created_at", desc=True).limit(500).execute()
        return [_record(row) for row in _rows(response.data)]

    def open_count(self) -> int:
        response = get_supabase().table("flags").select("id").eq("status", "open").execute()
        return len(_rows(response.data))

    def get(self, flag_id: str) -> FlagRecord | None:
        response = (
            get_supabase().table("flags").select(_COLUMNS).eq("id", flag_id).limit(1).execute()
        )
        rows = _rows(response.data)
        return _record(rows[0]) if rows else None

    def close(
        self,
        flag_id: str,
        *,
        status: Literal["resolved", "dismissed"],
        admin_note: str,
        admin_email: str,
        when: datetime,
    ) -> FlagRecord | None:
        response = (
            get_supabase()
            .table("flags")
            .update(
                {
                    "status": status,
                    "admin_note": admin_note,
                    "resolved_by": admin_email,
                    "resolved_at": when.isoformat(),
                    "student_seen_at": None,
                }
            )
            .eq("id", flag_id)
            .execute()
        )
        rows = _rows(response.data)
        return _record(rows[0]) if rows else None


_memory = MemoryFlagStore()


def get_flag_store() -> FlagStore:
    if settings.supabase_url and settings.supabase_service_role_key:
        return SupabaseFlagStore()
    return _memory
