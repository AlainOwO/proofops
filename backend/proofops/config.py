from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://proofops:proofops_local@127.0.0.1:55432/proofops"
    artifact_dir: Path = APP_ROOT / "artifacts"
    ai_mode: Literal["off", "live"] = "off"
    openai_api_key: SecretStr = SecretStr("")
    anthropic_api_key: SecretStr = SecretStr("")
    allowed_providers: str = ""
    cheap_provider: Literal["openai", "anthropic"] = "openai"
    cheap_model: str = ""
    strong_provider: Literal["openai", "anthropic"] = "anthropic"
    strong_model: str = ""
    model_prices_path: Path = APP_ROOT / "config/model_prices.json"
    rate_card_path: Path | None = None
    ai_budget_usd: str = "0"
    ai_max_task_cost_usd: str = "0"
    model_timeout_seconds: float = Field(default=20, gt=0, le=60)
    model_max_output_tokens: int = Field(default=1200, ge=64, le=4096)
    aws_account_id: str = ""
    aws_region: str = "ap-south-1"
    aws_profile: str = ""
    aws_cluster: str = ""
    aws_service: str = ""
    aws_log_group: str = ""
    aws_lookback_seconds: int = Field(default=3600, ge=60, le=86400)
    aws_max_calls: int = Field(default=12, ge=1, le=30)
    job_lease_seconds: int = Field(default=120, ge=30, le=600)
    job_timeout_seconds: int = Field(default=180, ge=30, le=600)
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    max_bundle_bytes: int = Field(default=5_242_880, ge=1024, le=20_971_520)
    max_artifact_bytes: int = Field(default=1_048_576, ge=1024, le=5_242_880)
    max_bundle_files: int = Field(default=24, ge=1, le=50)

    @field_validator("artifact_dir")
    @classmethod
    def owned_artifacts(cls, value: Path) -> Path:
        resolved = value.resolve()
        if not resolved.is_relative_to(APP_ROOT.resolve()) or resolved == APP_ROOT.resolve():
            raise ValueError("artifact_dir must be a dedicated directory inside the application")
        if not resolved.is_relative_to(APP_ROOT / "artifacts") or any(
            part in {"evaluation", "evaluator_only"}
            for part in resolved.relative_to(APP_ROOT).parts
        ):
            raise ValueError(
                "artifact_dir cannot overlap application code, trust or evaluator data"
            )
        return resolved

    @field_validator("model_prices_path")
    @classmethod
    def owned_prices(cls, value: Path) -> Path:
        resolved = value.resolve()
        if not resolved.is_relative_to(APP_ROOT / "config"):
            raise ValueError("model_prices_path must be inside the application's config directory")
        return resolved

    @field_validator("rate_card_path", mode="before")
    @classmethod
    def owned_rate_card(cls, value):
        if value is None or value == "":
            return None
        resolved = Path(value).resolve()
        if not resolved.is_relative_to(APP_ROOT) or any(
            part in {"evaluation", "evaluator_only", ".git"}
            for part in resolved.relative_to(APP_ROOT).parts
        ):
            raise ValueError(
                "rate_card_path must stay inside the application and outside evaluator storage"
            )
        return resolved

    @property
    def providers(self) -> set[str]:
        return {part.strip() for part in self.allowed_providers.split(",") if part.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
