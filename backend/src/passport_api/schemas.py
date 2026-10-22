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
