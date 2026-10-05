from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

APP_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: str = Field(
        default="postgresql+psycopg://proofops@127.0.0.1:55432/proofops", repr=False
    )
    artifact_dir: Path = APP_ROOT / "artifacts"
    proofops_mode: Literal["local", "hosted"] = "local"
    proofops_public_demo: bool = False
    secret_key: SecretStr = SecretStr("")
    proofops_admin_username: str = ""
    proofops_admin_password: SecretStr = SecretStr("")
    session_cookie_secure: bool = True
    session_ttl_seconds: int = Field(default=28_800, ge=60, le=86_400)
    login_window_seconds: int = Field(default=900, ge=60, le=3600)
    login_max_failures: int = Field(default=5, ge=3, le=10)
    login_max_ip_attempts: int = Field(default=60, ge=10, le=300)
    request_body_timeout_seconds: float = Field(default=10, gt=0, le=60)
    request_max_concurrency: int = Field(default=16, ge=1, le=128)
    request_max_peer_concurrency: int = Field(default=8, ge=1, le=64)
    request_max_principal_concurrency: int = Field(default=4, ge=1, le=32)
    request_max_login_concurrency: int = Field(default=2, ge=1, le=4)
    request_quota_window_seconds: int = Field(default=60, ge=1, le=3600)
    request_peer_quota: int = Field(default=600, ge=1, le=10000)
    request_principal_quota: int = Field(default=300, ge=1, le=10000)
    request_max_identities: int = Field(default=2048, ge=1, le=10000)
    request_max_buffered_bytes: int = Field(default=20_971_520, ge=1024, le=134_217_728)
    allowed_hosts: str = "127.0.0.1,localhost,api"
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

    def validate_database_security(self) -> None:
        if self.proofops_mode != "hosted":
            return
        try:
            url = make_url(self.database_url)
            password = url.password or ""
            compact = "".join(character for character in password.lower() if character.isalnum())
            valid = (
                url.get_backend_name() == "postgresql"
                and bool(url.username)
                and len(password) >= 32
                and len(set(password)) >= 16
                and not any(
                    word in compact for word in ("changeme", "replace", "example", "password")
                )
                and not {"password", "user", "service", "passfile"}.intersection(url.query)
            )
        except (ArgumentError, TypeError, ValueError):
            valid = False
        if not valid:
            raise ValueError(
                "Hosted database configuration requires a privately generated PostgreSQL "
                "password of at least 32 characters and 16 distinct characters, with no "
                "placeholder or credential query overrides."
            ) from None

    @model_validator(mode="after")
    def hosted_database(self) -> Self:
        self.validate_database_security()
        return self

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
