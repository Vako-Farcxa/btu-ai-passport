from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

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
    "student_email_taken",
    "pdf_already_exists",
    "skill_name_taken",
    "sheet_unavailable",
    "award_level_required",
    "duplicate_email",
    "invalid_comment",
    "flag_already_open",
    "flag_rate_limited",
    "flag_not_found",
    "passport_revoked",
    "version_revoked",
    "student_not_deleted",
    "version_already_revoked",
    "version_not_revoked",
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
    # Set when an admin revoked this version. None for a version in good standing.
    revoked_at: str | None = None


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
    revoked_at: datetime | None = None
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


# ---------------------------------------------------------------------------
# Skills catalog and awards
# ---------------------------------------------------------------------------

SkillLevel = Literal["AI Skill", "AI Applied Skill", "AI Advanced Skill"]
SkillName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class AdminMe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str


class AdminCatalogSkill(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    name_ka: str
    category: str
    badge: str
    description: str


class AdminCatalogSkillList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skills: list[AdminCatalogSkill]


class AdminCatalogSkillCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: SkillName
    name_ka: str = Field(default="", max_length=200)
    category: SkillLevel
    description: str = Field(default="", max_length=1000)


class AdminCatalogSkillUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: SkillName | None = None
    name_ka: str | None = Field(default=None, max_length=200)
    category: SkillLevel | None = None
    description: str | None = Field(default=None, max_length=1000)


class AwardStudent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=320)
    # Needed only when the student has no passport and no row in the sheet yet.
    first_name: str = Field(default="", max_length=100)
    last_name: str = Field(default="", max_length=100)
    # Also only for new students. Students who already have a row keep what they have.
    # IDs are never sent by the client: the server reuses or mints them.
    program: str = Field(default="", max_length=200)
    education_level: str = Field(default="", max_length=100)


class AdminAwardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str = Field(min_length=1, max_length=40)
    # Defaults to the skill's own category.
    level: SkillLevel | None = None
    awarded_on: date | None = None
    students: list[AwardStudent] = Field(min_length=1, max_length=50)


class AwardRowResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    status: Literal["synced", "failed", "pending", "skipped"]
    error: str = ""
    passport_id: str = ""
    version: str = ""


class AdminAwardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[AwardRowResult]
    sync_result: SyncResult


# ---------------------------------------------------------------------------
# Flags: a student reports a problem with one version of their passport
# ---------------------------------------------------------------------------

FlagStatus = Literal["open", "resolved", "dismissed"]


class FlagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    # The real limits (10 to 500 after trimming) are applied in the endpoint, so the answer
    # is a readable error code. This only keeps the body small.
    comment: str = Field(max_length=5000)


class StudentFlag(BaseModel):
    """A flag as its own student sees it. IDs and codes of the passport stay server side."""

    model_config = ConfigDict(extra="forbid")

    id: str
    version: int
    comment: str
    status: FlagStatus
    admin_note: str
    created_at: datetime
    resolved_at: datetime | None
    # An admin reply (resolved or dismissed) the student has not opened yet.
    unread: bool


class StudentFlagList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flags: list[StudentFlag]
    unread: int


class AdminFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    passport_id: str
    version: int
    verification_code: str
    student_email: str
    comment: str
    status: FlagStatus
    admin_note: str
    resolved_by: str | None
    created_at: datetime
    resolved_at: datetime | None


class AdminFlagList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flags: list[AdminFlag]
    # Open flags overall, whatever filter is applied. Shown on the dashboard.
    open_count: int


class AdminFlagUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["resolved", "dismissed"]
    admin_note: str = Field(default="", max_length=5000)
