from typing import Literal

from pydantic import BaseModel, ConfigDict

ErrorCode = Literal[
    "unauthorized",
    "domain_not_allowed",
    "code_required",
    "version_not_found",
    "pdf_not_ready",
    "sync_unauthorized",
]


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ErrorCode


class Skill(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill: str
    badge: str
    awarded_on: str | None


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
