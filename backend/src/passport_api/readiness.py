"""Readiness check behind GET /health/ready.

/health only says "the process is up" and touches nothing else, so a monitor can ping it every
few minutes to keep the free Render service awake. /health/ready asks the three things the app
depends on and reports each one:

- database: one tiny read through Supabase's REST API (the only dependency the site cannot do
  without, so it alone decides between 200 and 503),
- sheet: opens the Google spreadsheet (the sync and the admin awards need it),
- chain: asks the Amoy RPC for the latest block (anchoring and the on-chain badge need it).

Every check has a short timeout and the three run side by side, so the whole answer takes at
most `health_timeout_seconds`. The answer is cached for a minute (15 seconds when something is
down, so a recovery shows up quickly), which means pinging this URL cannot burn the Google
Sheets quota or a free RPC's request limit. The output holds only fixed words (status and a
short reason code), never an address, a key or an error message.
"""

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import UTC, datetime
from typing import Literal

import httpx
from web3 import Web3

from passport_api.schemas import ReadyComponent, ReadyReport
from passport_api.settings import settings
from passport_api.sync import SheetUnavailableError, open_spreadsheet

CACHE_OK_SECONDS = 60.0
CACHE_PROBLEM_SECONDS = 15.0
COMPONENTS = ("database", "sheet", "chain")

_executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="readiness")
_lock = threading.Lock()
_cached: tuple[float, ReadyReport] | None = None


def _clock() -> float:
    return time.monotonic()


def clear_cache() -> None:
    global _cached
    with _lock:
        _cached = None


def check_database(timeout: float) -> ReadyComponent:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return ReadyComponent(status="down", reason="not_configured")
    try:
        response = httpx.get(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/sync_runs",
            params={"select": "id", "limit": "1"},
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
            },
            timeout=timeout,
        )
    except httpx.TimeoutException:
        return ReadyComponent(status="down", reason="timeout")
    except httpx.HTTPError:
        return ReadyComponent(status="down", reason="unreachable")
    if response.status_code != 200:
        return ReadyComponent(status="down", reason=f"http_{response.status_code}")
    return ReadyComponent(status="ok")


def check_sheet(timeout: float) -> ReadyComponent:
    try:
        open_spreadsheet(timeout)
    except SheetUnavailableError as exc:
        if str(exc) == "sheet_not_configured":
            return ReadyComponent(status="not_configured")
        return ReadyComponent(status="down", reason="unreachable")
    return ReadyComponent(status="ok")


def check_chain(timeout: float) -> ReadyComponent:
    if not settings.amoy_rpc_url:
        return ReadyComponent(status="not_configured")
    try:
        provider = Web3.HTTPProvider(
            settings.amoy_rpc_url,
            request_kwargs={"timeout": timeout},
            exception_retry_configuration=None,
        )
        Web3(provider).eth.block_number  # noqa: B018 (the request itself is the check)
    except Exception as exc:
        name = type(exc).__name__.lower()
        return ReadyComponent(
            status="down", reason="timeout" if "timeout" in name else "unreachable"
        )
    return ReadyComponent(status="ok")


def _guarded(check: Callable[[float], ReadyComponent], timeout: float) -> ReadyComponent:
    try:
        return check(timeout)
    except Exception:
        # Whatever went wrong, the message may hold a URL. Report only that it failed.
        return ReadyComponent(status="down", reason="error")


def overall_status(
    components: dict[str, ReadyComponent],
) -> Literal["ok", "degraded", "down"]:
    if components["database"].status != "ok":
        return "down"
    if any(item.status == "down" for item in components.values()):
        return "degraded"
    return "ok"


def run_checks() -> ReadyReport:
    timeout = settings.health_timeout_seconds
    checks = {"database": check_database, "sheet": check_sheet, "chain": check_chain}
    futures = {name: _executor.submit(_guarded, fn, timeout) for name, fn in checks.items()}
    deadline = _clock() + timeout + 1.0
    components: dict[str, ReadyComponent] = {}
    for name in COMPONENTS:
        try:
            components[name] = futures[name].result(timeout=max(0.0, deadline - _clock()))
        except FutureTimeout:
            components[name] = ReadyComponent(status="down", reason="timeout")
    return ReadyReport(
        status=overall_status(components),
        components=components,
        checked_at=datetime.now(UTC),
    )


def readiness() -> ReadyReport:
    """The cached report, or a fresh one when the cache is older than its time to live.

    One caller at a time refreshes it; the others wait for that answer instead of starting
    their own checks."""
    global _cached
    with _lock:
        now = _clock()
        if _cached is not None and _cached[0] > now:
            return _cached[1]
        report = run_checks()
        ttl = CACHE_OK_SECONDS if report.status == "ok" else CACHE_PROBLEM_SECONDS
        _cached = (_clock() + ttl, report)
        return report
