import logging
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from passport_api.chain import bytes32
from passport_api.errors import APIError
from passport_api.fingerprint import content_hash, verification_id_hash
from passport_api.onchain import OnchainCheck, OnchainVerifier, contract_address, contract_url
from passport_api.schemas import Skill
from passport_api.store import StoredVersion, VersionStore

_log = logging.getLogger(__name__)

EXPLORER = "https://amoy.polygonscan.com/tx/"


class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(max_length=64)


class OnchainInfo(BaseModel):
    """What the on-chain check found, plus what anyone needs to repeat it on Polygonscan.

    status "verified": the contract holds exactly the hash recomputed from the stored passport.
    status "unavailable": the chain could not be read just now. Nothing is claimed about it.
    """

    model_config = ConfigDict(extra="forbid")

    status: str
    block_number: int | None
    contract_address: str
    contract_url: str
    # Key to paste into the contract's `anchors` function, and the value it must return.
    verification_id_hash: str
    content_hash: str


class VerifyFound(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: str
    holder_name: str
    version: int
    is_latest: bool
    skills: list[Skill]
    tx_url: str
    onchain: OnchainInfo


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


class VerifyTampered(BaseModel):
    """The stored passport does not match its hash (in the database or on the blockchain).
    Carries no name and no skills: the content cannot be trusted, so none of it is shown."""

    model_config = ConfigDict(extra="forbid")

    outcome: str
    # stored_content_changed: the stored fields no longer hash to the stored content_hash.
    # chain_mismatch: the contract holds a different hash for this code.
    # not_on_chain: the database says confirmed but the contract holds nothing for this code.
    reason: str
    contract_url: str


class VerifyError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: str


VerifyResult = (
    VerifyFound
    | VerifyOutdated
    | VerifyRevoked
    | VerifyNotFound
    | VerifyPending
    | VerifyTampered
    | VerifyError
)


def verify_code(
    store: VersionStore, raw_code: str, chain: OnchainVerifier | None = None
) -> VerifyResult:
    """Look a code up and check it. `chain` is the on-chain reader, or None when there is none
    (the result then carries the "check unavailable" badge)."""
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
    if not found.tx_hash or not found.content_hash:
        # Confirmed without a transaction or a stored hash is inconsistent data, not a
        # normal state.
        return VerifyError(outcome="error")
    # 1. The stored passport must still hash to the hash stored with it.
    recomputed = content_hash(
        holder_name=found.holder_name,
        passport_id=found.passport_id,
        skills=found.skills,
        version=found.version,
    )
    if recomputed.lower() != found.content_hash.lower():
        return _tampered(found, "stored_content_changed")
    # 2. The contract must hold that same hash for this code.
    onchain = _onchain(found, recomputed, chain)
    if onchain.status == "mismatch":
        return _tampered(found, "chain_mismatch")
    if onchain.status == "missing":
        return _tampered(found, "not_on_chain")
    latest = store.latest_version(found.passport_id)
    is_latest = found.version >= latest.version
    fields = {
        "holder_name": found.holder_name,
        "version": found.version,
        "is_latest": is_latest,
        "skills": list(found.skills),
        "tx_url": f"{EXPLORER}{found.tx_hash}",
        "onchain": OnchainInfo(
            status="verified" if onchain.status == "verified" else "unavailable",
            block_number=onchain.block_number,
            contract_address=contract_address(),
            contract_url=contract_url(),
            verification_id_hash=_code_hash(found.verification_code),
            content_hash=recomputed,
        ),
    }
    if is_latest:
        return VerifyFound(outcome="valid", **fields)
    return VerifyOutdated(
        outcome="outdated",
        latest_version=latest.version,
        latest_issued_at=latest.issued_on,
        **fields,
    )


def _code_hash(raw_code: str) -> str:
    return verification_id_hash(raw_code)


def _onchain(found: StoredVersion, expected: str, chain: OnchainVerifier | None) -> OnchainCheck:
    if chain is None:
        return OnchainCheck("unavailable")
    try:
        return chain.check(
            bytes32(_code_hash(found.verification_code)),
            bytes32(expected),
            tx_hash=found.tx_hash,
            anchored_age_seconds=_age_seconds(found.anchored_at),
        )
    except Exception:
        # The check must never turn a readable database result into a server error.
        _log.warning("onchain_check_failed", exc_info=True)
        return OnchainCheck("unavailable")


def _age_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return (datetime.now(UTC) - moment).total_seconds()


def _tampered(found: StoredVersion, reason: str) -> VerifyTampered:
    # Loud on purpose: this is either an attack, a manual database edit or a bug.
    _log.error(
        "verify_tampered passport=%s version=%s reason=%s",
        found.passport_id,
        found.version,
        reason,
    )
    return VerifyTampered(outcome="tampered", reason=reason, contract_url=contract_url())
