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


settings = Settings()
