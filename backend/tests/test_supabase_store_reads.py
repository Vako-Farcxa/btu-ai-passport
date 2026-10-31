"""SupabaseStore row mapping and the JWKS fetch, driven by canned PostgREST responses."""

from types import SimpleNamespace
from typing import Any

import httpx
import pytest

import passport_api.auth as auth
import passport_api.supabase_store as store_mod
from passport_api.api.verify import get_store
from passport_api.errors import APIError
from passport_api.settings import settings
from passport_api.store import MemoryStore
from passport_api.supabase_store import SupabaseStore


class CannedClient:
    """Returns the same rows for any select and remembers what was asked for."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.filters: list[tuple[str, object]] = []

    def table(self, _name: str) -> "CannedClient":
        return self

    def select(self, _columns: str) -> "CannedClient":
        return self

    def eq(self, column: str, value: object) -> "CannedClient":
        self.filters.append((column, value))
        return self

    def limit(self, _n: int) -> "CannedClient":
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self.rows)


def _version_row(number: int, *, revoked: str | None = None) -> dict[str, Any]:
    return {
        "version_number": number,
        "holder_name": "Nino Beridze",
        "verification_code": f"BTU-AAAA-000{number}",
        "anchor_status": "anchored",
        "tx_hash": "0x" + "ab" * 32,
        "issued_at": f"2026-10-0{number}T10:00:00+00:00",
        "pdf_en_path": None,
        "pdf_ka_path": None,
        "revoked_at": revoked,
        "content_hash": None,
        "anchored_at": None,
        "skill_entries": [
            {
                "skill": "SQL",
                "badge": "Gold",
                "awarded_on": None,
                "description": None,
                "position": 1,
            },
            {
                "skill": "Git",
                "badge": "Silver",
                "awarded_on": "2026-09-01",
                "description": "Branching",
                "position": 0,
            },
        ],
    }


def _student_row(*versions: dict[str, Any], deleted_at: str | None = None) -> dict[str, Any]:
    return {
        "id": "s-1",
        "email": "nino@btu.edu.ge",
        "full_name": "Nino Beridze",
        "passport_id": "BTU-2026-0001",
        "deleted_at": deleted_at,
        "passport_versions": list(versions),
    }


def _use(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]]) -> CannedClient:
    client = CannedClient(rows)
    monkeypatch.setattr(store_mod, "get_supabase", lambda: client)
    return client


def test_find_normalizes_the_code_and_maps_skills_in_position_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _version_row(1)
    row["students"] = {
        "email": "nino@btu.edu.ge",
        "full_name": "Nino Beridze",
        "passport_id": "BTU-2026-0001",
        "deleted_at": None,
    }
    client = _use(monkeypatch, [row])

    found = SupabaseStore().find("  btu-aaaa-0001 ")

    assert client.filters == [("verification_code", "BTU-AAAA-0001")]
    assert found is not None
    assert [skill.skill for skill in found.skills] == ["Git", "SQL"]
    assert found.skills[1].description == ""
    assert found.skills[1].awarded_on is None
    assert found.skills[0].awarded_on == "2026-09-01"
    assert found.version_revoked_at is None
    assert found.student_archived_at is None


def test_find_returns_none_when_nothing_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, [])
    assert SupabaseStore().find("BTU-NOPE-0000") is None


def test_max_and_latest_version_pick_the_highest_number(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, [_student_row(_version_row(2), _version_row(1), _version_row(3))])
    store = SupabaseStore()

    assert store.max_version("BTU-2026-0001") == 3
    latest = store.latest_version("BTU-2026-0001")
    assert latest.version == 3
    assert latest.issued_on == "2026-10-03"


def test_latest_version_without_an_issue_date_uses_the_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _version_row(1)
    row["issued_at"] = None
    _use(monkeypatch, [_student_row(row)])
    assert SupabaseStore().latest_version("BTU-2026-0001").issued_on == "1970-01-01"


def test_unknown_passport_id_raises_key_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, [])
    store = SupabaseStore()
    with pytest.raises(KeyError):
        store.max_version("BTU-2026-9999")
    with pytest.raises(KeyError):
        store.latest_version("BTU-2026-9999")


@pytest.mark.parametrize(
    ("rows", "archived"),
    [
        ([], False),
        ([{"deleted_at": None}], False),
        ([{"deleted_at": "2026-10-01T00:00:00+00:00"}], True),
    ],
)
def test_is_archived(
    monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]], archived: bool
) -> None:
    client = _use(monkeypatch, rows)
    assert SupabaseStore().is_archived(" Nino@BTU.edu.ge ") is archived
    assert client.filters == [("email", "nino@btu.edu.ge")]


def test_versions_for_email_carries_the_student_onto_each_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use(
        monkeypatch,
        [
            _student_row(
                _version_row(1, revoked="2026-10-05T00:00:00+00:00"),
                _version_row(2),
                deleted_at="2026-10-06T00:00:00+00:00",
            )
        ],
    )

    versions = SupabaseStore().versions_for_email("nino@btu.edu.ge")

    assert [v.version for v in versions] == [1, 2]
    assert {v.passport_id for v in versions} == {"BTU-2026-0001"}
    assert versions[0].version_revoked_at is not None
    assert versions[1].version_revoked_at is None
    assert all(v.student_archived_at for v in versions)


def test_versions_for_email_is_empty_for_unknown_or_malformed_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use(monkeypatch, [])
    assert SupabaseStore().versions_for_email("who@btu.edu.ge") == ()

    malformed = _student_row()
    malformed["passport_versions"] = None
    _use(monkeypatch, [malformed])
    assert SupabaseStore().versions_for_email("nino@btu.edu.ge") == ()

    mixed = _student_row(_version_row(1))
    mixed["passport_versions"].append("not a row")
    _use(monkeypatch, [mixed])
    assert len(SupabaseStore().versions_for_email("nino@btu.edu.ge")) == 1


def test_verify_route_uses_supabase_only_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_service_role_key", "")
    assert isinstance(get_store(), MemoryStore)

    monkeypatch.setattr(settings, "supabase_url", "https://x.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "service-key")
    assert isinstance(get_store(), SupabaseStore)


class _Response:
    def __init__(self, payload: object, status: int = 200) -> None:
        self._payload = payload
        self._status = status

    def raise_for_status(self) -> None:
        if self._status >= 400:
            raise httpx.HTTPStatusError(
                "bad", request=httpx.Request("GET", "https://x"), response=httpx.Response(500)
            )

    def json(self) -> object:
        return self._payload


def test_fetch_jwks_returns_the_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "supabase_url", "https://x.supabase.co/")
    seen: list[str] = []

    def fake_get(url: str, timeout: float) -> _Response:
        seen.append(url)
        return _Response({"keys": []})

    monkeypatch.setattr(httpx, "get", fake_get)
    assert auth.fetch_jwks() == {"keys": []}
    assert seen == ["https://x.supabase.co/auth/v1/.well-known/jwks.json"]


@pytest.mark.parametrize("payload", [["not", "a", "dict"], "text"])
def test_fetch_jwks_rejects_a_body_that_is_not_an_object(
    monkeypatch: pytest.MonkeyPatch, payload: object
) -> None:
    monkeypatch.setattr(settings, "supabase_url", "https://x.supabase.co")
    monkeypatch.setattr(httpx, "get", lambda url, timeout: _Response(payload))
    with pytest.raises(APIError) as caught:
        auth.fetch_jwks()
    assert caught.value.status_code == 401


def test_fetch_jwks_maps_network_and_http_errors_to_unauthorized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "supabase_url", "https://x.supabase.co")

    def boom(url: str, timeout: float) -> _Response:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", boom)
    with pytest.raises(APIError) as caught:
        auth.fetch_jwks()
    assert caught.value.status_code == 401

    monkeypatch.setattr(httpx, "get", lambda url, timeout: _Response({}, status=500))
    with pytest.raises(APIError):
        auth.fetch_jwks()


def test_fetch_jwks_without_a_project_url_is_unauthorized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "supabase_url", "")
    with pytest.raises(APIError):
        auth.fetch_jwks()
