"""Run the real FastAPI backend with seeded fixture data, for the real-backend browser tests.

    uv run python scripts/serve_e2e.py            # http://127.0.0.1:8000

The browser tests in frontend/e2e-real/ run against this process with nothing mocked in the
browser: the real routes, validation, CORS, security headers and rate limiter all run. Only the
two outside services are replaced by in-process stand-ins:

- the database is the in-memory store (the same one the demo mode uses), seeded below,
- the blockchain is a small scripted contract that returns the hashes listed below.

It needs no secrets and refuses to start when any real service is configured, so it can never
read or write real data. Never deploy it.
"""

import os
import sys
from dataclasses import replace

# Never inherit a real configuration (a developer's backend/.env, a CI secret). Setting an
# empty value here beats the .env file, because environment variables win in pydantic-settings.
FORCED = {
    "SUPABASE_URL": "",
    "SUPABASE_SERVICE_ROLE_KEY": "",
    "SYNC_TOKEN": "",
    "SHEET_ID": "",
    "GOOGLE_SERVICE_ACCOUNT_JSON": "",
    "AMOY_RPC_URL": "",
    "BTU_ISSUER_PRIVATE_KEY": "",
    "DEMO_MODE": "true",
    "CORS_ORIGINS": '["http://localhost:3000"]',
    "RATE_LIMIT_VERIFY_PER_MINUTE": "1000",
}
if __name__ == "__main__":
    # Only when run as a server: importing this file (the tests do) must not touch the
    # environment of the importing process.
    for name, value in FORCED.items():
        os.environ[name] = value

import uvicorn  # noqa: E402

from passport_api.api import verify as verify_api  # noqa: E402
from passport_api.chain import ZERO, bytes32  # noqa: E402
from passport_api.demo_data import DEMO_VERSIONS  # noqa: E402
from passport_api.fingerprint import content_hash, verification_id_hash  # noqa: E402
from passport_api.onchain import OnchainVerifier  # noqa: E402
from passport_api.schemas import Skill  # noqa: E402
from passport_api.store import MemoryStore, StoredVersion  # noqa: E402

# Codes the browser tests use. The first three come from the built-in demo data:
#   VALID     latest version of Nino Beridze's passport, anchored, chain check "verified"
#   OUTDATED  her version 1, an older version, still anchored
#   PENDING   anchor not confirmed yet
VALID = "A1B2-C3D4-E5F6-G7H8"
OUTDATED = "K9M2-N3P4-Q5R6-S7T8"
PENDING = "V2W3-X4Y5-Z6A7-B8C9"
REVOKED = "R3V0-K3D0-0000-0001"
TAMPERED = "T4MP-3RED-0000-0002"
CHAIN_MISMATCH = "C4A1-N0FF-0000-0003"

_MOMENT = "2026-10-20T12:00:00Z"


def _anchored(version: StoredVersion) -> StoredVersion:
    return replace(version, anchored_at=_MOMENT)


def _fixture(code: str, name: str, passport_id: str, email: str) -> StoredVersion:
    skills = (Skill(skill="Prompt Engineering", badge="BDG-AI-002", awarded_on="2026-09-01"),)
    return StoredVersion(
        passport_id=passport_id,
        email=email,
        full_name=name,
        version=1,
        holder_name=name,
        verification_code=code,
        anchor_status="confirmed",
        tx_hash="0x" + "33" * 32,
        issued_at="2026-09-02T00:00:00Z",
        skills=skills,
        content_hash=content_hash(
            holder_name=name, passport_id=passport_id, skills=skills, version=1
        ),
        anchored_at=_MOMENT,
    )


def build_versions() -> list[StoredVersion]:
    revoked = replace(
        _fixture(REVOKED, "Revoked Student", "BTU-R3V0K3D000", "revoked@btu.edu.ge"),
        version_revoked_at="2026-10-25T09:00:00Z",
    )
    # The stored name was edited after the hash was made: the database check catches it.
    tampered = replace(
        _fixture(TAMPERED, "Original Name", "BTU-T4MP3R0000", "tampered@btu.edu.ge"),
        holder_name="Someone Else",
    )
    mismatch = _fixture(CHAIN_MISMATCH, "Chain Mismatch", "BTU-C4A1N0FF00", "chain@btu.edu.ge")
    return [*(_anchored(v) for v in DEMO_VERSIONS), revoked, tampered, mismatch]


class ScriptedContract:
    """The PassportAnchor contract as a dictionary: verification id hash -> content hash."""

    def __init__(self, versions: list[StoredVersion]) -> None:
        self.slots: dict[bytes, bytes] = {}
        for version in versions:
            if version.anchor_status != "confirmed" or not version.content_hash:
                continue
            self.slots[bytes32(verification_id_hash(version.verification_code))] = bytes32(
                version.content_hash
            )
        # The contract holds a different hash for this code than the database does.
        self.slots[bytes32(verification_id_hash(CHAIN_MISMATCH))] = bytes.fromhex("ab" * 32)

    def read_anchor(self, verification_id_hash: bytes) -> bytes:
        return self.slots.get(verification_id_hash, ZERO)

    def block_of(self, tx_hash: str) -> int | None:
        return 4242


def main() -> None:
    # Safety net on top of FORCED: stop if anything real is still configured.
    from passport_api.settings import settings

    if settings.supabase_url or settings.amoy_rpc_url or settings.sheet_id:
        sys.exit("serve_e2e.py refuses to run with a real service configured")

    versions = build_versions()
    store = MemoryStore(versions)
    verifier = OnchainVerifier(ScriptedContract(versions))
    verify_api.get_store = lambda: store
    verify_api.verifier_from_settings = lambda: verifier  # type: ignore[attr-defined]

    from passport_api.main import app

    uvicorn.run(
        app,
        host=os.environ.get("E2E_BACKEND_HOST", "127.0.0.1"),
        port=int(os.environ.get("E2E_BACKEND_PORT", "8000")),
        log_level="warning",
    )


if __name__ == "__main__":
    main()
