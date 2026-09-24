
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str

    # Kod inceleme ajanı (agents/reviewer.py) — hepsi isteğe bağlı
    REVIEWER_PROVIDER: str = "ollama"
    REVIEWER_MODEL: str = ""
    # Asıl sağlayıcı çalışmazsa buna düşülür (boş bırakılırsa yedek yok)
    REVIEWER_FALLBACK: str = "ollama"
    GEMINI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()