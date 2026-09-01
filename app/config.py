from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    mongo_url: str = "mongodb://localhost:27017"
    db_name: str = "quizwizai"
    secret_key: str = "dev-secret-key-change-in-production"
    anthropic_api_key: str = ""  # unused in CLI mode; kept for optional API-key fallback
    session_expiry_days: int = 7
    gmail_user: str = ""
    gmail_app_password: str = ""
    frontend_url: str = "https://quizwizai.netlify.app"

    # Text-only AI generation: quiz/flashcard/study-guide creation, grading, and
    # AI Tutor replies when no image is attached.
    ai_text_provider: str = "claude"  # "claude" or "openrouter"
    openrouter_text_model: str = "qwen/qwen3-30b-a3b-instruct-2507"

    # Vision AI generation: worksheet/photo/PDF scanning and AI Tutor replies
    # when a homework photo is attached. Configured separately from text above
    # since vision quality on messy handwriting varies more between models.
    ai_vision_provider: str = "claude"  # "claude" or "openrouter"
    openrouter_vision_model: str = "qwen/qwen2.5-vl-72b-instruct"

    openrouter_api_key: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings():
    return Settings()
