from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Réglages lus depuis les variables d'environnement préfixées PIANO_ (ou backend/.env)."""

    model_config = SettingsConfigDict(env_prefix="PIANO_", env_file=BACKEND_DIR / ".env")

    storage_dir: Path = BACKEND_DIR / "storage"
    max_upload_mb: int = 200
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    @property
    def database_url(self) -> str:
        return f"sqlite:///{(self.storage_dir / 'app.db').as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
