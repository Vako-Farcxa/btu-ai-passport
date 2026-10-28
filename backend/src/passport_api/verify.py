from pydantic import BaseModel, ConfigDict, Field

from passport_api.errors import APIError
from passport_api.schemas import Skill
from passport_api.store import VersionStore

EXPLORER = "https://amoy.polygonscan.com/tx/"


class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(max_length=64)


class VerifyFound(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: str
    holder_name: str
    version: int
    is_latest: bool
    skills: list[Skill]
    tx_url: str


class VerifyOutdated(VerifyFound):
    """Outdated result. Says that a newer version exists, never its code."""

    latest_version: int
    latest_issued_at: str


class VerifyNotFound(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: str


class VerifyError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: str


def verify_code(
    store: VersionStore, raw_code: str
) -> VerifyFound | VerifyOutdated | VerifyNotFound | VerifyError:
    if not raw_code.strip():
        raise APIError(422, "code_required")
    found = store.find(raw_code)
    if found is None:
        return VerifyNotFound(outcome="not_found")
    if found.anchor_status != "confirmed" or not found.tx_hash:
        return VerifyError(outcome="error")
    latest = store.latest_version(found.passport_id)
    is_latest = found.version >= latest.version
    fields = {
        "holder_name": found.holder_name,
        "version": found.version,
        "is_latest": is_latest,
        "skills": list(found.skills),
        "tx_url": f"{EXPLORER}{found.tx_hash}",
    }
    if is_latest:
        return VerifyFound(outcome="valid", **fields)
    return VerifyOutdated(
        outcome="outdated",
        latest_version=latest.version,
        latest_issued_at=latest.issued_on,
        **fields,
    )
