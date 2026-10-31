"""Every error answer has the same body, `{"code": ...}`, including malformed input."""

import pytest
from fastapi.testclient import TestClient

import passport_api.api.admin as admin_mod
from passport_api.main import app

client = TestClient(app)


def test_a_malformed_verify_body_is_a_standard_error() -> None:
    for body in ({}, {"code": 5}, {"code": None}):
        response = client.post("/verify", json=body)
        assert response.status_code == 422
        assert response.json() == {"code": "invalid_request"}


def test_the_answer_never_echoes_what_was_sent() -> None:
    marker = "do-not-echo-this-value"
    response = client.post("/verify", json={"code": [marker]})
    assert response.status_code == 422
    assert marker not in response.text


def test_an_unreadable_body_is_the_same_error() -> None:
    response = client.post(
        "/verify", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert (response.status_code, response.json()) == (422, {"code": "invalid_request"})


def test_a_bad_query_parameter_on_an_admin_route_is_the_same_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(admin_mod, "require_admin", lambda _auth: "admin@btu.edu.ge")
    response = client.get("/admin/audit?limit=abc", headers={"Authorization": "Bearer x"})
    assert (response.status_code, response.json()) == (422, {"code": "invalid_request"})


def test_a_blank_code_keeps_its_own_more_specific_code() -> None:
    response = client.post("/verify", json={"code": "  "})
    assert response.json() == {"code": "code_required"}


def test_auth_errors_run_before_body_validation_and_keep_their_codes() -> None:
    response = client.post("/admin/skills", json={"nonsense": True})
    assert (response.status_code, response.json()) == (401, {"code": "unauthorized"})
