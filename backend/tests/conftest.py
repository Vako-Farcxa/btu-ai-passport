from collections.abc import Iterator

import pytest

from passport_api.settings import Settings, settings


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Run every test on defaults, never on a developer's backend/.env."""
    defaults = Settings(_env_file=None)
    for name in Settings.model_fields:
        monkeypatch.setattr(settings, name, getattr(defaults, name))
    yield
