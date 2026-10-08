from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    # SSH tunnel: ssh -L 5432:localhost:5432 core@acrossthe.cloud
    database_url: str = "postgresql+asyncpg://coastguard:CHANGE_ME@localhost:5432/coastguard"


settings = Settings()
