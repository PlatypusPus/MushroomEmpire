from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    database_url: str = "postgresql+asyncpg://coastguard:CHANGE_ME@acrossthe.cloud:5432/coastguard"
    default_event_id: int = 5  # Hurricane Nicole, Nov 2022: the proposed demo event (ROOT_CONTEXT 20.2a)
    # LLM (LiteLLM model string, e.g. "ollama/qwen2.5:3b"). Swap providers via .env.
    llm_model: str = "ollama/qwen2.5:3b"
    ollama_base_url: str = "http://localhost:11434"
    llm_api_key: str = ""
    llm_timeout_s: float = Field(default=180, gt=0)  # first call loads the model into memory
    llm_temperature: float = Field(default=0.2, ge=0, le=2)
    llm_chat_timeout_s: float = Field(default=60, gt=0)  # per-question budget for the grounded assistant
    llm_chat_max_tokens: int = Field(default=220, gt=0)  # answers are capped at 4 short sentences
    llm_brief_max_tokens: int = Field(default=120, gt=0)  # briefings are 2 to 3 sentences, under 60 words
    llm_brief_model: str = "ollama/qwen2.5:3b"  # constrained paraphrase: non-thinking model (qwen3 thinks in a
    # separate field and burns small token budgets on reasoning, leaving empty content)

    # Accounts: Google OAuth 2.0 authorization-code flow with PKCE. jwt_secret signs our own session token.
    google_client_id: str = ""
    google_client_secret: str = ""  # confidential: only ever used server-side in the code exchange
    github_client_id: str = ""
    github_client_secret: str = ""  # confidential, same rule
    # Origin the BROWSER uses (the Vite dev server proxies /api to the backend). Google redirects back to <this>/api/auth/google/callback.
    app_origin: str = "http://localhost:5173"
    jwt_secret: str = ""  # required to enable accounts; generate with: python -c "import secrets;print(secrets.token_urlsafe(48))"
    jwt_ttl_h: int = 24 * 7
    # Alert email. With no smtp_host, mails are written to backend/outbox/ instead (still recorded as delivered=outbox).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    live_alert_poll_s: int = 600


settings = Settings()
