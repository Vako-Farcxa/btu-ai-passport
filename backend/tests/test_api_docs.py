"""The API docs are only served when ENABLE_API_DOCS is on."""

import pytest
from fastapi.testclient import TestClient

from passport_api.main import app, create_app
from passport_api.settings import Settings

DOC_PATHS = ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"]


def test_docs_are_off_by_default() -> None:
    assert Settings(_env_file=None).enable_api_docs is False


@pytest.mark.skipif(Settings().enable_api_docs, reason="docs are enabled in this environment")
def test_the_running_app_hides_the_docs() -> None:
    client = TestClient(app)
    for path in DOC_PATHS:
        assert client.get(path).status_code == 404, path


def test_docs_can_be_turned_on_for_local_use() -> None:
    client = TestClient(create_app(enable_docs=True))
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_turning_docs_off_leaves_the_api_working() -> None:
    client = TestClient(create_app(enable_docs=False))
    for path in DOC_PATHS:
        assert client.get(path).status_code == 404, path
    assert app.openapi()["paths"]
