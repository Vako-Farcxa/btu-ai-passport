from supabase import Client, create_client

from passport_api.settings import settings


def get_supabase() -> Client:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("supabase_not_configured")
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
