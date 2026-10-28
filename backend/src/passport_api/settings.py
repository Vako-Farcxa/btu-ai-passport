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
    # Comma-separated email domains accepted for sign-in and sheet rows.
    allowed_email_domains: str = "btu.edu.ge"
    # Local demos only. Accepts the "demo-admin" bearer token on /admin. Never set it on a
    # deployed backend.
    demo_mode: bool = False
    # Serves /docs, /redoc and /openapi.json. Off by default so a deployed API does not
    # publish its route map. Turn it on locally with ENABLE_API_DOCS=true.
    enable_api_docs: bool = False


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
