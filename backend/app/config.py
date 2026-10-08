from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    database_url: str = "postgresql+asyncpg://coastguard:CHANGE_ME@acrossthe.cloud:5432/coastguard"
    default_event_id: int = 5  # Hurricane Nicole, Nov 2022: the proposed demo event (ROOT_CONTEXT 20.2a)
    # LLM (LiteLLM model string, e.g. "ollama/qwen3:4b"). Swap providers via .env.
    llm_model: str = "ollama/qwen3:4b"
    ollama_base_url: str = "http://localhost:11434"
    llm_api_key: str = ""
    llm_timeout_s: float = Field(default=60, gt=0)
    llm_temperature: float = Field(default=0.2, ge=0, le=2)


settings = Settings()
