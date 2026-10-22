from fastapi import APIRouter
from fastapi.responses import JSONResponse

from passport_api.demo_data import DEMO_VERSIONS
from passport_api.settings import settings
from passport_api.store import MemoryStore, VersionStore
from passport_api.verify import VerifyRequest, verify_code

router = APIRouter()


def get_store() -> VersionStore:
    if settings.supabase_url and settings.supabase_service_role_key:
        from passport_api.supabase_store import SupabaseStore

        return SupabaseStore()
    return MemoryStore(DEMO_VERSIONS)


@router.post("/verify")
def verify(body: VerifyRequest) -> JSONResponse:
    result = verify_code(get_store(), body.code)
    return JSONResponse(status_code=200, content=result.model_dump())
