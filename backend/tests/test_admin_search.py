"""Admin student search: user input must never change the shape of the PostgREST filter."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import passport_api.api.admin as admin_mod
from passport_api.main import app
from passport_api.search import (
    MAX_SEARCH_LENGTH,
    clean_search_term,
    contains_filter,
    escape_like,
    quote_postgrest_value,
)

client = TestClient(app)


def test_percent_underscore_and_backslash_match_themselves() -> None:
    assert escape_like("100%") == "100\\%"
    assert escape_like("a_b") == "a\\_b"
    assert escape_like("a\\b") == "a\\\\b"
    assert escape_like("plain") == "plain"


def test_quoting_keeps_reserved_characters_as_text() -> None:
    assert quote_postgrest_value("a,b") == '"a,b"'
    assert quote_postgrest_value('say "hi"') == '"say \\"hi\\""'
    assert quote_postgrest_value("a\\b") == '"a\\\\b"'


def test_cleaning_removes_control_characters_wildcard_alias_and_extra_length() -> None:
    assert clean_search_term("  ada\n\t\x00lovelace  ") == "adalovelace"
    assert clean_search_term("a*b") == "ab"
    assert clean_search_term("x" * 500) == "x" * MAX_SEARCH_LENGTH


def test_an_empty_search_adds_no_filter() -> None:
    assert contains_filter(["email"], "") is None
    assert contains_filter(["email"], "  \n * ") is None


def test_a_normal_search_filters_both_columns() -> None:
    assert (
        contains_filter(["email", "full_name"], "ada")
        == 'email.ilike."%ada%",full_name.ilike."%ada%"'
    )


@pytest.mark.parametrize(
    "attack",
    [
        "x,deleted_at.is.null",
        "x),and(email.eq.admin@btu.edu.ge",
        "x.eq.1",
        "a%",
        "_",
        'x",deleted_at.is.null,"',
    ],
)
def test_injection_attempts_stay_inside_one_quoted_pattern(attack: str) -> None:
    result = contains_filter(["email", "full_name"], attack)
    assert result is not None
    # Exactly two conditions, whatever the user typed: one per column.
    assert result.startswith("email.ilike.")
    first, sep, second = result.partition(",full_name.ilike.")
    assert sep
    for pattern in (first.removeprefix("email.ilike."), second):
        assert pattern.startswith('"%') and pattern.endswith('%"')
        inner = pattern[1:-1]
        # Every quote or backslash typed by the user is escaped, so the value cannot close
        # its own quotes.
        unescaped = inner.replace("\\\\", "").replace('\\"', "")
        assert '"' not in unescaped


def _list(search: str) -> Any:
    with patch("passport_api.api.admin.get_supabase") as mock_db:
        query = MagicMock()
        mock_db.return_value.table.return_value.select.return_value = query
        for name in ("is_", "or_", "order", "range"):
            getattr(query, name).return_value = query
        query.execute.return_value.data = []
        query.execute.return_value.count = 0
        mock_db.return_value.table.return_value.select.return_value.is_.return_value = query
        response = client.get("/admin/students", params={"search": search})
    return response, query


def test_the_route_sends_the_escaped_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin_mod, "require_admin", lambda _auth: "admin@btu.edu.ge")
    response, query = _list("50%_off,deleted_at.is.null")
    assert response.status_code == 200
    query.or_.assert_called_once_with(
        'email.ilike."%50\\\\%\\\\_off,deleted\\\\_at.is.null%",'
        'full_name.ilike."%50\\\\%\\\\_off,deleted\\\\_at.is.null%"'
    )


def test_a_blank_search_sends_no_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin_mod, "require_admin", lambda _auth: "admin@btu.edu.ge")
    response, query = _list("   ")
    assert response.status_code == 200
    query.or_.assert_not_called()
