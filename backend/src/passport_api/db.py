import threading

from supabase import Client, create_client

from passport_api.settings import settings

# One client per (url, key) for the whole process. Building a client for every call meant a
# new TCP and TLS connection for every query (three round trips before the first byte), which
# made a sync of a few hundred students spend most of its time connecting. The client holds a
# thread-safe connection pool, so request threads and the sync share it and reuse connections.
_clients: dict[tuple[str, str], Client] = {}
_lock = threading.Lock()


def get_supabase() -> Client:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("supabase_not_configured")
    key = (settings.supabase_url, settings.supabase_service_role_key)
    client = _clients.get(key)
    if client is None:
        with _lock:
            client = _clients.get(key)
            if client is None:
                client = create_client(*key)
                _clients[key] = client
    return client


def reset_client() -> None:
    """Forget the cached clients (tests, and after the settings change)."""
    with _lock:
        _clients.clear()
