from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    DATABASE_URL: str
    REDIS_URL: str
    SECRET_KEY: str


    @field_validator("DATABASE_URL")
    @classmethod
    def use_asyncpg(cls, v: str) -> str:
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return v.replace(prefix, "postgresql+asyncpg://", 1)
        return v


settings = Settings()