from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    database_url: str = "postgresql+asyncpg://coastguard:CHANGE_ME@acrossthe.cloud:5432/coastguard"
    default_event_id: int = 1  # event whose snapshot answers reads when none is given


settings = Settings()
