from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from passport_api.api.verify import router as verify_router
from passport_api.errors import APIError
from passport_api.schemas import ErrorBody
from passport_api.settings import settings

app = FastAPI(title="BTU AI Skills Digital Passport API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(verify_router)


@app.exception_handler(APIError)
def handle_api_error(_request: Request, exc: APIError) -> JSONResponse:
    body = ErrorBody(code=exc.code)
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
