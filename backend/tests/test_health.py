"""/health (liveness) and /health/ready (readiness)."""

import http.server
import threading
import time
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from web3 import Web3

import passport_api.readiness as readiness
from passport_api.main import app
from passport_api.schemas import ReadyComponent
from passport_api.settings import settings
from passport_api.sync import SheetUnavailableError

client = TestClient(app)
OK = ReadyComponent(status="ok")


def _down(reason: str = "unreachable") -> ReadyComponent:
    return ReadyComponent(status="down", reason=reason)


@pytest.fixture(autouse=True)
def fresh_cache() -> Iterator[None]:
    readiness.clear_cache()
    yield
    readiness.clear_cache()


def _checks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    database: ReadyComponent = OK,
    sheet: ReadyComponent = OK,
    chain: ReadyComponent = OK,
    calls: list[str] | None = None,
) -> None:
    def make(name: str, result: ReadyComponent) -> Any:
        def check(_timeout: float) -> ReadyComponent:
            if calls is not None:
                calls.append(name)
            return result

        return check

    monkeypatch.setattr(readiness, "check_database", make("database", database))
    monkeypatch.setattr(readiness, "check_sheet", make("sheet", sheet))
    monkeypatch.setattr(readiness, "check_chain", make("chain", chain))


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_touches_no_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    _checks(monkeypatch, calls=calls)
    assert client.get("/health").status_code == 200
    assert calls == []


def test_health_answers_head_too() -> None:
    # Some uptime monitors check with HEAD.
    assert client.head("/health").status_code == 200
    assert client.head("/health/ready").status_code in (200, 503)


def test_ready_reports_every_component(monkeypatch: pytest.MonkeyPatch) -> None:
    _checks(monkeypatch)
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["components"] == {
        "database": {"status": "ok"},
        "sheet": {"status": "ok"},
        "chain": {"status": "ok"},
    }
    assert "checked_at" in body
    assert response.headers["cache-control"] == "no-store"


def test_ready_is_503_when_the_database_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    _checks(monkeypatch, database=_down("timeout"))
    response = client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "down"
    assert body["components"]["database"] == {"status": "down", "reason": "timeout"}


@pytest.mark.parametrize("which", ["sheet", "chain"])
def test_ready_stays_200_but_degraded_when_only_sheet_or_chain_is_down(
    monkeypatch: pytest.MonkeyPatch, which: str
) -> None:
    _checks(
        monkeypatch,
        sheet=_down() if which == "sheet" else OK,
        chain=_down() if which == "chain" else OK,
    )
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["components"][which]["status"] == "down"


def test_not_configured_sheet_or_chain_is_not_a_problem(monkeypatch: pytest.MonkeyPatch) -> None:
    unset = ReadyComponent(status="not_configured")
    _checks(monkeypatch, sheet=unset, chain=unset)
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready_without_any_configuration_is_503() -> None:
    # Defaults: no Supabase key. Nothing can be reached, and nothing may crash.
    response = client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["components"]["database"] == {"status": "down", "reason": "not_configured"}
    assert body["components"]["sheet"] == {"status": "not_configured"}
    assert body["components"]["chain"] == {"status": "not_configured"}


def test_ready_is_cached_for_a_minute(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    _checks(monkeypatch, calls=calls)
    now = [1000.0]
    monkeypatch.setattr(readiness, "_clock", lambda: now[0])
    for _ in range(5):
        assert client.get("/health/ready").status_code == 200
    assert sorted(calls) == ["chain", "database", "sheet"]
    now[0] += readiness.CACHE_OK_SECONDS - 1
    client.get("/health/ready")
    assert len(calls) == 3
    now[0] += 2
    client.get("/health/ready")
    assert len(calls) == 6


def test_a_problem_is_cached_for_a_shorter_time(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    _checks(monkeypatch, database=_down(), calls=calls)
    now = [1000.0]
    monkeypatch.setattr(readiness, "_clock", lambda: now[0])
    client.get("/health/ready")
    client.get("/health/ready")
    assert len(calls) == 3
    now[0] += readiness.CACHE_PROBLEM_SECONDS + 1
    client.get("/health/ready")
    assert len(calls) == 6
    assert readiness.CACHE_PROBLEM_SECONDS < readiness.CACHE_OK_SECONDS


def test_ready_is_not_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    _checks(monkeypatch)
    for _ in range(150):
        assert client.get("/health/ready").status_code == 200
        assert client.get("/health").status_code == 200


def test_a_slow_check_is_reported_as_a_timeout_quickly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "health_timeout_seconds", 0.2)
    _checks(monkeypatch)

    def slow(_timeout: float) -> ReadyComponent:
        time.sleep(1.5)
        return OK

    monkeypatch.setattr(readiness, "check_sheet", slow)
    started = time.monotonic()
    response = client.get("/health/ready")
    assert time.monotonic() - started < 1.4
    assert response.status_code == 200
    assert response.json()["components"]["sheet"] == {"status": "down", "reason": "timeout"}
    assert response.json()["status"] == "degraded"


def test_ready_never_leaks_urls_or_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "supabase_url", "https://secret-project.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "SERVICE-KEY-123")
    monkeypatch.setattr(settings, "amoy_rpc_url", "https://rpc.example/KEY-IN-URL-456")
    monkeypatch.setattr(settings, "sheet_id", "SHEET-ID-789")

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("failed for https://secret-project.supabase.co SERVICE-KEY-123")

    monkeypatch.setattr(httpx, "get", boom)
    monkeypatch.setattr(readiness, "open_spreadsheet", boom)
    monkeypatch.setattr(Web3, "HTTPProvider", boom)
    response = client.get("/health/ready")
    text = response.text
    for secret in ("secret-project", "SERVICE-KEY", "KEY-IN-URL", "SHEET-ID", "https://"):
        assert secret not in text
    assert response.json()["components"]["database"]["reason"] == "error"
    assert response.json()["components"]["sheet"]["reason"] == "error"
    assert response.json()["components"]["chain"]["reason"] == "unreachable"


# -- the individual checks -------------------------------------------------------------


class _Handler(http.server.BaseHTTPRequestHandler):
    seen: list[tuple[str, str | None, str | None]] = []
    status = 200
    delay = 0.0

    def do_GET(self) -> None:
        type(self).seen.append(
            (self.path, self.headers.get("apikey"), self.headers.get("Authorization"))
        )
        time.sleep(type(self).delay)
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"[]")

    def log_message(self, format: str, *args: Any) -> None:
        return


@pytest.fixture
def fake_supabase(monkeypatch: pytest.MonkeyPatch) -> Iterator[type[_Handler]]:
    _Handler.seen = []
    _Handler.status = 200
    _Handler.delay = 0.0
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(settings, "supabase_url", f"http://127.0.0.1:{server.server_port}/")
    monkeypatch.setattr(settings, "supabase_service_role_key", "service-key")
    yield _Handler
    server.shutdown()
    server.server_close()


def test_database_check_does_one_tiny_read(fake_supabase: type[_Handler]) -> None:
    assert readiness.check_database(2.0) == OK
    assert fake_supabase.seen == [
        ("/rest/v1/sync_runs?select=id&limit=1", "service-key", "Bearer service-key")
    ]


def test_database_check_reports_a_refusal_by_status_code(fake_supabase: type[_Handler]) -> None:
    fake_supabase.status = 401
    assert readiness.check_database(2.0) == _down("http_401")


def test_database_check_times_out(fake_supabase: type[_Handler]) -> None:
    fake_supabase.delay = 1.0
    started = time.monotonic()
    assert readiness.check_database(0.2) == _down("timeout")
    assert time.monotonic() - started < 0.9


def test_database_check_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "supabase_url", "http://127.0.0.1:9")
    monkeypatch.setattr(settings, "supabase_service_role_key", "k")
    assert readiness.check_database(1.0) == _down("unreachable")


def test_sheet_check(monkeypatch: pytest.MonkeyPatch) -> None:
    assert readiness.check_sheet(1.0) == ReadyComponent(status="not_configured")
    seen: list[float | None] = []
    monkeypatch.setattr(readiness, "open_spreadsheet", lambda timeout=None: seen.append(timeout))
    assert readiness.check_sheet(2.5) == OK
    assert seen == [2.5]

    def refuse(timeout: float | None = None) -> None:
        raise SheetUnavailableError("sheet_unavailable")

    monkeypatch.setattr(readiness, "open_spreadsheet", refuse)
    assert readiness.check_sheet(1.0) == _down("unreachable")


def test_chain_check(monkeypatch: pytest.MonkeyPatch) -> None:
    assert readiness.check_chain(1.0) == ReadyComponent(status="not_configured")
    monkeypatch.setattr(settings, "amoy_rpc_url", "http://127.0.0.1:9")
    assert readiness.check_chain(1.0) == _down("unreachable")

    class Eth:
        block_number = 123

    class FakeWeb3:
        eth = Eth()

        def __init__(self, _provider: object) -> None:
            return

        @staticmethod
        def HTTPProvider(*_args: Any, **_kwargs: Any) -> None:  # noqa: N802
            return None

    monkeypatch.setattr("passport_api.readiness.Web3", FakeWeb3)
    assert readiness.check_chain(1.0) == OK


def test_chain_check_timeout_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "amoy_rpc_url", "http://127.0.0.1:9")

    class ReadTimeout(Exception):  # noqa: N818
        pass

    def boom(*_a: Any, **_k: Any) -> Any:
        raise ReadTimeout("x")

    monkeypatch.setattr(Web3, "HTTPProvider", boom)
    assert readiness.check_chain(1.0) == _down("timeout")
