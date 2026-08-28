"""Application configuration loaded from environment variables (.env supported)."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central, environment-based configuration. No secrets hard-coded."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM provider selection (independent backends) ---
    llm_provider: str = "gemini"  # gemini | openrouter
    # Gemini (independent)
    gemini_api_key: str | None = None
    model_name: str = "gemini-3-flash-preview"
    llm_timeout_seconds: float = 60.0
    # OpenRouter (independent — OpenAI-compatible)
    openrouter_api_key: str | None = None
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_site_url: str | None = None  # optional HTTP-Referer
    openrouter_app_name: str | None = None  # optional X-Title
    openrouter_timeout_seconds: float = 60.0

    # --- Database (SQLite default; Postgres-ready) ---
    database_url: str = "sqlite:///./job_switch_agent.db"

    # --- Phase 2/4: job discovery providers ---
    enable_remotive: bool = True
    enable_arbeitnow: bool = False
    enable_jobicy: bool = False
    adzuna_app_id: str | None = None
    adzuna_api_key: str | None = None
    greenhouse_companies: str = ""  # comma-separated ATS board tokens
    provider_timeout_seconds: float = 10.0
    max_provider_retries: int = 2
    job_cache_ttl_minutes: int = 60
    url_verify_ttl_hours: int = 24
    url_verify_max_per_search: int = 10
    job_stale_days: int = 30
    job_search_max_queries: int = 5
    job_search_results_per_query: int = 15
    job_match_weights_json: str = json.dumps(
        {
            "required_skill_match": 0.35,
            "preferred_skill_match": 0.15,
            "role_match": 0.15,
            "experience_match": 0.15,
            "location_match": 0.10,
            "salary_match": 0.10,
        }
    )
    ranking_top_n: int = 20
    ranking_min_experience_ratio: float = 0.4
    dedupe_title_threshold: float = 0.80
    dedupe_description_threshold: float = 0.85

    # --- Phase 3: application copilot ---
    cover_letter_min_words: int = 250
    cover_letter_max_words: int = 550

    # --- Roadmap / scoring knobs ---
    roadmap_days: int = 30
    daily_study_hours: float = Field(default=2.0)
    match_weights_json: str = json.dumps(
        {
            "required_skills": 0.50,
            "preferred_skills": 0.20,
            "experience": 0.15,
            "project_relevance": 0.10,
            "education": 0.05,
        }
    )

    # --- LangSmith tracing (optional) ---
    # https://smith.langchain.com — set LANGSMITH_TRACING=true + LANGCHAIN_API_KEY to enable.
    # LANGCHAIN_* aliases are supported for backwards compat.
    langsmith_tracing: bool = False
    langsmith_api_key: str | None = None
    langchain_api_key: str | None = None  # alias for LANGCHAIN_API_KEY
    langsmith_project: str = "job-switch-agent"
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    # --- Arize Phoenix tracing (optional, local) ---
    # https://docs.arize.com/phoenix — run locally: docker run -p 6006:6006 arizephoenix/phoenix
    phoenix_tracing: bool = False
    phoenix_endpoint: str = "http://localhost:6006/v1/traces"
    phoenix_project: str = "job-switch-agent"

    # --- Auth / JWT (basic) ---
    secret_key: str = "change-me-in-prod-use-env-SECRET_KEY"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # --- Uploads / API ---
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB
    allowed_upload_types: tuple[str, ...] = ("application/pdf", "text/plain")
    cors_origins: str = "http://localhost:3000"

    @property
    def match_weights(self) -> dict[str, float]:
        weights: dict[str, Any] = self._load_json_dict(
            self.match_weights_json, "MATCH_WEIGHTS_JSON"
        )
        expected = {"required_skills", "preferred_skills", "experience", "project_relevance", "education"}
        if set(weights) != expected:
            raise ValueError(f"MATCH_WEIGHTS_JSON keys must be exactly {sorted(expected)}")
        total = sum(float(w) for w in weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"MATCH_WEIGHTS_JSON must sum to 1.0 (got {total})")
        return {k: float(v) for k, v in weights.items()}

    @property
    def job_match_weights(self) -> dict[str, float]:
        weights: dict[str, Any] = self._load_json_dict(
            self.job_match_weights_json, "JOB_MATCH_WEIGHTS_JSON"
        )
        expected = {
            "required_skill_match", "preferred_skill_match", "role_match",
            "experience_match", "location_match", "salary_match",
        }
        if set(weights) != expected:
            raise ValueError(f"JOB_MATCH_WEIGHTS_JSON keys must be exactly {sorted(expected)}")
        total = sum(float(w) for w in weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"JOB_MATCH_WEIGHTS_JSON must sum to 1.0 (got {total})")
        return {k: float(v) for k, v in weights.items()}

    @staticmethod
    def _load_json_dict(raw: str, name: str) -> dict[str, Any]:
        try:
            data: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError as exc:  # pragma: no cover - config error path
            raise ValueError(f"{name} is not valid JSON") from exc
        return data

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor; tests can override via env or monkeypatching."""
    return Settings()
