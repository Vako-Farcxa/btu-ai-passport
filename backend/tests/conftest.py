import dataclasses
from collections.abc import Iterator

import pytest

import passport_api.anchoring as anchoring
import passport_api.auth as auth
from passport_api.ratelimit import limits
from passport_api.settings import Settings, settings

# Tests that mint their own tokens put this project URL in `iss`: TEST_ISSUER.
TEST_SUPABASE_URL = "https://test-project.supabase.co"
TEST_ISSUER = f"{TEST_SUPABASE_URL}/auth/v1"


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Run every test on defaults, never on a developer's backend/.env."""
    defaults = Settings(_env_file=None)
    for name in Settings.model_fields:
        monkeypatch.setattr(settings, name, getattr(defaults, name))
    # Token checks need to know which project issued the token. There is no service key
    # here, so nothing else treats Supabase as configured.
    monkeypatch.setattr(settings, "supabase_url", TEST_SUPABASE_URL)
    auth.clear_jwks_cache()
    limits.reset()
    yield
    auth.clear_jwks_cache()
    limits.reset()


@pytest.fixture(autouse=True)
def quick_anchor_settle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never really wait for receipts in tests: poll once and move on."""
    monkeypatch.setattr(
        anchoring, "DEFAULT_POLICY", dataclasses.replace(anchoring.DEFAULT_POLICY, settle_seconds=0)
    )
