import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from passport_api.api.admin import router as admin_router
from passport_api.api.flags import admin_router as flags_admin_router
from passport_api.api.flags import router as flags_router
from passport_api.api.health import router as health_router
from passport_api.api.me import router as me_router
from passport_api.api.sync import router as sync_router
from passport_api.api.verify import router as verify_router
from passport_api.errors import APIError
from passport_api.schemas import ErrorBody
from passport_api.security_headers import SecurityHeadersMiddleware
from passport_api.settings import settings

# One readable line per log entry (time, level, logger, message). It does nothing when the server
# or a test has already set logging up.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(*, enable_docs: bool) -> FastAPI:
    """Build the API. With docs off, /docs, /redoc and /openapi.json do not exist (404)."""
    return FastAPI(
        title="BTU AI Skills Digital Passport API",
        docs_url="/docs" if enable_docs else None,
        redoc_url="/redoc" if enable_docs else None,
        openapi_url="/openapi.json" if enable_docs else None,
    )


app = create_app(enable_docs=settings.enable_api_docs)

# Only the real frontend origin(s) from CORS_ORIGINS may call the API from a browser, and only
# with the methods and headers the app uses. The frontend sends a bearer token, never cookies.
# Retry-After is exposed so the page can tell the user how long to wait after a 429.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Retry-After"],
    max_age=600,
)
# Added last, so it wraps everything, CORS preflights and error responses included.
app.add_middleware(
    SecurityHeadersMiddleware,
    docs_paths=("/docs", "/redoc", "/openapi.json") if settings.enable_api_docs else (),
)

app.include_router(health_router)
app.include_router(verify_router)
app.include_router(me_router)
app.include_router(sync_router)
app.include_router(admin_router)
app.include_router(flags_router)
app.include_router(flags_admin_router)


@app.exception_handler(APIError)
def handle_api_error(_request: Request, exc: APIError) -> JSONResponse:
    body = ErrorBody(code=exc.code)
    return JSONResponse(status_code=exc.status_code, content=body.model_dump(), headers=exc.headers)


@app.exception_handler(RequestValidationError)
def handle_invalid_request(_request: Request, _exc: RequestValidationError) -> JSONResponse:
    """Malformed input gets the same `{code}` body as every other error. FastAPI's default
    answer lists each field and echoes the value that was sent, which the app never needs."""
    body = ErrorBody(code="invalid_request")
    return JSONResponse(status_code=422, content=body.model_dump())
