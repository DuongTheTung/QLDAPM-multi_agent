from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    frontend_origin: str = "http://localhost:5173"

    nine_router_base_url: str = "http://localhost:20128/v1"
    nine_router_api_key: str = ""
    nine_router_models: str = (
        "cx/gpt-5.6-sol,ag/gemini-3.8-flash-medium,gc/gemini-3-pro-preview"
    )
    nine_router_image_model: str = "ag/gemini-3-pro-image-preview"
    llm_timeout_seconds: int = 180
    max_revisions: int = 3

    data_dir: Path = Path(__file__).resolve().parents[1] / "data"

    @property
    def models(self) -> list[str]:
        return [model.strip() for model in self.nine_router_models.split(",") if model.strip()]

    @property
    def database_path(self) -> Path:
        return self.data_dir / "comicflow.db"

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    return settings

