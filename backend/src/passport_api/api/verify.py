from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from passport_api.demo_data import DEMO_VERSIONS
from passport_api.onchain import verifier_from_settings
from passport_api.ratelimit import client_ip, enforce
from passport_api.settings import settings
from passport_api.store import MemoryStore, VersionStore
from passport_api.verify import VerifyRequest, verify_code

router = APIRouter()


def get_store() -> VersionStore:
    if settings.supabase_url and settings.supabase_service_role_key:
        from passport_api.supabase_store import SupabaseStore

        return SupabaseStore()
    return MemoryStore(DEMO_VERSIONS)


def limit_verify(request: Request) -> None:
    """Public and unauthenticated, so it is limited per client IP (30 a minute by default)."""
    enforce("verify", client_ip(request), settings.rate_limit_verify_per_minute)


@router.post("/verify", dependencies=[Depends(limit_verify)])
def verify(body: VerifyRequest) -> JSONResponse:
    result = verify_code(get_store(), body.code, verifier_from_settings())
    return JSONResponse(status_code=200, content=result.model_dump())
