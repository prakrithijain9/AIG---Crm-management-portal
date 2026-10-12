"""Application settings, loaded from environment variables (or backend/.env)."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AIG CRM API"
    environment: str = "development"

    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "postgres"
    # SecretStr keeps the password out of logs and reprs.
    db_password: SecretStr = SecretStr("")
    db_name: str = "aig_crm_dev"
    # Separate database used only by the test suite (same server and role).
    test_db_name: str = "aig_crm_test"

    # Comma-separated list of origins allowed to call the API (the Next.js dev server).
    cors_origins: str = "http://localhost:3000"

    def url_for(self, database: str) -> URL:
        # URL.create escapes special characters in the password safely.
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.db_user,
            password=self.db_password.get_secret_value() or None,
            host=self.db_host,
            port=self.db_port,
            database=database,
        )

    @property
    def database_url(self) -> URL:
        return self.url_for(self.db_name)

    @property
    def test_database_url(self) -> URL:
        return self.url_for(self.test_db_name)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
