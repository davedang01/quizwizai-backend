from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    mongo_url: str = "mongodb://localhost:27017"
    db_name: str = "quizwizai"
    secret_key: str = "dev-secret-key-change-in-production"
    anthropic_api_key: str = "sk-placeholder"
    session_expiry_days: int = 7
    gmail_user: str = ""
    gmail_app_password: str = ""
    frontend_url: str = "http://localhost:5173"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings():
    return Settings()
