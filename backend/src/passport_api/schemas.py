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
    "rate_limited",
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
    student_id: str = Field(default="", max_length=100)
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
