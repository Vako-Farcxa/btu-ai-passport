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


class VerifyRevoked(BaseModel):
    """Revoked result. Deliberately carries no name and no skills: a revoked record may have
    been issued to the wrong person or by mistake, so it is not shown any more."""

    model_config = ConfigDict(extra="forbid")

    outcome: str
    revoked_at: str


class VerifyPending(BaseModel):
    """The code exists but its on-chain anchor is not confirmed yet (first transaction in
    flight, retrying after a failure, or waiting for an admin). Carries no name and no skills:
    nothing is vouched for until the anchor is confirmed."""

    model_config = ConfigDict(extra="forbid")

    outcome: str


class VerifyError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: str


def verify_code(
    store: VersionStore, raw_code: str
) -> VerifyFound | VerifyOutdated | VerifyRevoked | VerifyNotFound | VerifyPending | VerifyError:
    if not raw_code.strip():
        raise APIError(422, "code_required")
    found = store.find(raw_code)
    if found is None:
        return VerifyNotFound(outcome="not_found")
    # Revocation outranks everything else, including a pending or failed anchor.
    revoked_at = found.revoked_at
    if revoked_at is not None:
        return VerifyRevoked(outcome="revoked", revoked_at=revoked_at)
    if found.anchor_status != "confirmed":
        # Pending, retrying and exhausted anchors all read the same to the public. The
        # reconciler keeps working on them and admins see the detail.
        return VerifyPending(outcome="pending")
    if not found.tx_hash:
        # Confirmed without a transaction hash is inconsistent data, not a normal state.
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
