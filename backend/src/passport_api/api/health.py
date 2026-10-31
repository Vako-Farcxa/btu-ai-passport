"""Public health endpoints. Neither one is rate limited, so a monitor can ping them freely.

HEAD is answered too, because some uptime monitors check with HEAD instead of GET.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from passport_api.readiness import readiness

router = APIRouter(tags=["health"])

# Monitors and CDNs must always see the live answer, never a copy.
_NO_STORE = {"Cache-Control": "no-store"}


@router.get("/health")
@router.head("/health", include_in_schema=False)
def health() -> JSONResponse:
    """Liveness: the process is running. Touches no dependency, so it is always cheap."""
    return JSONResponse({"status": "ok"}, headers=_NO_STORE)


@router.get("/health/ready")
@router.head("/health/ready", include_in_schema=False)
def health_ready() -> JSONResponse:
    """Readiness: database, Google Sheet and Amoy RPC, each "ok", "down" or "not_configured".

    200 while the database works (even when the Sheet or the chain is down, then the overall
    status is "degraded"), 503 when the database does not. Cached for about a minute."""
    report = readiness()
    return JSONResponse(
        report.model_dump(mode="json", exclude_none=True),
        status_code=503 if report.status == "down" else 200,
        headers=_NO_STORE,
    )
