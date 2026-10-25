from pydantic_settings import BaseSettings,SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    DATABASE_URL : str
    REDIS_URL : str
    SECRET_KEY : str


settings = Settings()        