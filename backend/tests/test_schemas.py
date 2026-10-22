import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from passport_api.errors import APIError
from passport_api.main import app
from passport_api.schemas import ErrorBody, Skill


def test_error_body_accepts_contract_codes() -> None:
    codes = (
        "unauthorized",
        "domain_not_allowed",
        "code_required",
        "version_not_found",
        "pdf_not_ready",
        "sync_unauthorized",
    )
    for code in codes:
        assert ErrorBody(code=code).model_dump() == {"code": code}


def test_error_body_rejects_unknown_code() -> None:
    with pytest.raises(ValidationError):
        ErrorBody(code="nope")


def test_skill_keeps_empty_badge_and_null_date() -> None:
    skill = Skill(skill="Python", badge="", awarded_on=None)
    assert skill.model_dump() == {"skill": "Python", "badge": "", "awarded_on": None}


def test_api_error_returns_only_the_code() -> None:
    def raise_domain() -> None:
        raise APIError(403, "domain_not_allowed")

    app.add_api_route("/_test/domain", raise_domain, methods=["GET"])
    response = TestClient(app).get("/_test/domain")
    assert response.status_code == 403
    assert response.json() == {"code": "domain_not_allowed"}
