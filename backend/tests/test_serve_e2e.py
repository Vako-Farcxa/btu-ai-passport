"""The fixture server behind the real-backend browser tests (backend/scripts/serve_e2e.py).

The browser tests assert on what these fixtures answer, so the answers are pinned here, fast
and without a browser: if the verification rules change, this fails first and says which
fixture no longer means what the browser tests think it means.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from passport_api.onchain import OnchainVerifier
from passport_api.store import MemoryStore
from passport_api.verify import (
    VerifyFound,
    VerifyNotFound,
    VerifyOutdated,
    VerifyPending,
    VerifyResult,
    VerifyRevoked,
    VerifyTampered,
    verify_code,
)

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "serve_e2e.py"


@pytest.fixture(scope="module")
def serve_e2e():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("serve_e2e", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["serve_e2e"] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop("serve_e2e", None)


def _check(serve_e2e, code: str) -> VerifyResult:  # type: ignore[no-untyped-def]
    versions = serve_e2e.build_versions()
    verifier = OnchainVerifier(serve_e2e.ScriptedContract(versions))
    return verify_code(MemoryStore(versions), code, verifier)


def test_valid_and_outdated_codes_are_verified_on_the_scripted_chain(serve_e2e) -> None:  # type: ignore[no-untyped-def]
    valid = _check(serve_e2e, serve_e2e.VALID)
    assert isinstance(valid, VerifyFound)
    assert valid.onchain.status == "verified"
    assert valid.onchain.block_number == 4242
    outdated = _check(serve_e2e, serve_e2e.OUTDATED)
    assert isinstance(outdated, VerifyOutdated)
    assert outdated.latest_version == 2
    assert outdated.onchain.status == "verified"


def test_the_other_fixtures_cover_every_remaining_outcome(serve_e2e) -> None:  # type: ignore[no-untyped-def]
    assert isinstance(_check(serve_e2e, serve_e2e.PENDING), VerifyPending)
    assert isinstance(_check(serve_e2e, serve_e2e.REVOKED), VerifyRevoked)
    assert isinstance(_check(serve_e2e, "ZZZZ-ZZZZ-ZZZZ-ZZZZ"), VerifyNotFound)
    edited = _check(serve_e2e, serve_e2e.TAMPERED)
    assert isinstance(edited, VerifyTampered)
    assert edited.reason == "stored_content_changed"
    mismatch = _check(serve_e2e, serve_e2e.CHAIN_MISMATCH)
    assert isinstance(mismatch, VerifyTampered)
    assert mismatch.reason == "chain_mismatch"


def test_importing_the_script_does_not_change_the_environment() -> None:
    import os

    before = dict(os.environ)
    spec = importlib.util.spec_from_file_location("serve_e2e_again", SCRIPT)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(importlib.util.module_from_spec(spec))
    assert dict(os.environ) == before
