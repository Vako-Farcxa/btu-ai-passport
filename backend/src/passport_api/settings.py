from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = ""
    supabase_service_role_key: str = ""
    sync_token: str = ""
    cors_origins: list[str] = ["http://localhost:3000"]
    sheet_id: str = ""
    google_service_account_json: str = ""
    pdf_storage_dir: str = ""
    amoy_rpc_url: str = ""
    anchor_contract_address: str = ""
    btu_issuer_private_key: str = ""
    # The public verify page also reads the anchored hash back from the contract. It needs
    # only AMOY_RPC_URL (and the contract address, which defaults to the published one).
    # Turn it off with ONCHAIN_VERIFY=false. The timeout is per RPC request, in seconds.
    onchain_verify: bool = True
    onchain_timeout_seconds: float = 3.0
    # Comma-separated email domains accepted for sign-in and sheet rows.
    allowed_email_domains: str = "btu.edu.ge"
    # Local demos only. Accepts the "demo-admin" bearer token on /admin. Never set it on a
    # deployed backend.
    demo_mode: bool = False
    # Serves /docs, /redoc and /openapi.json. Off by default so a deployed API does not
    # publish its route map. Turn it on locally with ENABLE_API_DOCS=true.
    enable_api_docs: bool = False
    # Rate limits (in memory, per process, one-minute window). 0 turns a limit off,
    # RATE_LIMIT_ENABLED=false turns them all off.
    rate_limit_enabled: bool = True
    rate_limit_verify_per_minute: int = 30  # per client IP
    rate_limit_flags_per_minute: int = 5  # per signed-in student
    rate_limit_admin_writes_per_minute: int = 30  # per admin
    # How many proxies in front of this app add themselves to X-Forwarded-For. The client
    # address is the entry that many places from the right. 0 ignores the header (local
    # runs). On Render the right value is 3: Cloudflare, Render's edge and its load balancer.
    trusted_proxy_hops: int = 0


settings = Settings()


def allowed_domains() -> list[str]:
    return [
        part.strip().lower().lstrip("@")
        for part in settings.allowed_email_domains.split(",")
        if part.strip()
    ]


def email_domain_allowed(email: str) -> bool:
    _, at, domain = email.strip().lower().rpartition("@")
    return bool(at) and domain in allowed_domains()
