import pytest

from passport_api.db import get_supabase
from passport_api.settings import settings


def test_supabase_client_requires_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_service_role_key", "")
    with pytest.raises(RuntimeError, match="supabase_not_configured"):
        get_supabase()
