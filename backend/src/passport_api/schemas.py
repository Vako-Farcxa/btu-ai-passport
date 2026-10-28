from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ErrorCode = Literal[
    "unauthorized",
    "domain_not_allowed",
    "code_required",
    "version_not_found",
    "pdf_not_ready",
    "sync_unauthorized",
    "admin_not_found",
    "student_not_found",
    "skill_not_found",
    "student_already_deleted",
    "anchor_already_confirmed",
    "sheet_managed_student",
    "student_email_taken",
    "pdf_already_exists",
]


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ErrorCode


class Skill(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill: str
    badge: str
    awarded_on: str | None
    # Display only. Not part of the fingerprint or the anchored content hash.
    description: str = ""
    # Link to the skills catalog (sheet "Skill ID"). Not part of the fingerprint or the
    # anchored content hash, and not returned by the API.
    skill_id: str | None = Field(default=None, exclude=True)


class Anchor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["pending", "confirmed", "failed"]
    tx_url: str | None


class PassportVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    issued_at: str
    is_current: bool
    holder_name: str
    verification_code: str
    skills: list[Skill]
    anchor: Anchor


class Passport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passport_id: str
    versions: list[PassportVersion]


class PassportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passport: Passport | None


class SyncResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["completed", "skipped", "failed"]
    rows_read: int
    versions_created: int
    error: str | None = None


# ---------------------------------------------------------------------------
# Admin schemas
# ---------------------------------------------------------------------------


class AdminSkillEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    skill: str
    badge: str
    awarded_on: str | None
    description: str
    position: int


class AdminVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    version_number: int
    holder_name: str
    verification_code: str
    anchor_status: Literal["pending", "confirmed", "failed"]
    tx_hash: str | None
    issued_at: datetime
    pdf_en_path: str | None
    pdf_ka_path: str | None
    skills: list[AdminSkillEntry]


class AdminStudent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    email: str
    full_name: str
    passport_id: str
    admin_managed: bool
    deleted_at: datetime | None
    version_count: int
    latest_anchor_status: Literal["pending", "confirmed", "failed"] | None
    created_at: datetime


class AdminStudentDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    email: str
    full_name: str
    passport_id: str
    admin_managed: bool
    deleted_at: datetime | None
    created_at: datetime
    versions: list[AdminVersion]


class AdminStudentList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    students: list[AdminStudent]
    total: int


class AdminStudentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    full_name: str


class AdminSkillAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill: str
    badge: str = ""
    awarded_on: date | None = None


class AdminSyncRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    status: Literal["running", "completed", "skipped", "failed"]
    started_at: datetime
    finished_at: datetime | None
    rows_read: int | None
    versions_created: int | None
    error: str | None


class AdminSyncRunList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runs: list[AdminSyncRun]


class AdminVersionPending(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_id: UUID
    passport_id: str
    holder_name: str
    version_number: int
    anchor_status: Literal["pending", "failed"]
    issued_at: datetime
    tx_hash: str | None


class AdminVersionPendingList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    versions: list[AdminVersionPending]
