from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    database_url: str = "postgresql+asyncpg://coastguard:CHANGE_ME@acrossthe.cloud:5432/coastguard"
    default_event_id: int = 1  # event whose snapshot answers reads when none is given
    local_tz: str = "America/New_York"  # alert times are shown in the deep region's wall clock
    # LLM (LiteLLM model string, e.g. "ollama/qwen3:4b"). Swap providers via .env.
    llm_model: str = "ollama/qwen3:4b"
    ollama_base_url: str = "http://localhost:11434"
    llm_api_key: str = ""
    llm_timeout_s: float = Field(default=60, gt=0)
    llm_temperature: float = Field(default=0.2, ge=0, le=2)


settings = Settings()
