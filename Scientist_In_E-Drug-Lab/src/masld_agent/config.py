"""Configuration loading for competition / scoring / providers."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from masld_agent.models import DiseaseScope

PKG_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COMPETITION = PKG_ROOT / "config" / "competition_life_science.yaml"
DEFAULT_SCORING = PKG_ROOT / "config" / "scoring.yaml"


SCOPE_WARNING = (
    "competition_scope_warning: The public competition page emphasizes MASLD "
    "(hepatic lipid overload / lipotoxicity), while some submission templates mention "
    "HCC/new liver-cancer targets. Do NOT conflate the two disease directions. "
    "Confirm the final disease scope with the organizing committee before submission. "
    "Default runtime disease is MASLD; set --disease HCC only intentionally."
)


class LLMSettings(BaseModel):
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "MASLD_LLM_API_KEY"
    model: str = "gpt-4o-mini"
    timeout: float = 60.0
    temperature: float = 0.2


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    masld_http_cache_dir: str = ".cache/http"
    masld_competition_eval_mode: bool = True
    ncbi_email: Optional[str] = None
    masld_llm_base_url: str = "https://api.openai.com/v1"
    masld_llm_api_key: Optional[str] = None
    masld_llm_model: str = "gpt-4o-mini"
    masld_llm_timeout: float = 60.0
    masld_llm_temperature: float = 0.2


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_competition_config(path: Optional[Path] = None) -> dict[str, Any]:
    p = path or DEFAULT_COMPETITION
    data = load_yaml(p)
    data.setdefault("competition_scope_warning", SCOPE_WARNING)
    data.setdefault("disease_default", DiseaseScope.MASLD.value)
    data.setdefault(
        "hermes_eval_mode",
        {
            "disable_auto_skill_mutation": True,
            "disable_auto_workflow_update": True,
            "disable_uncontrolled_long_term_memory": True,
        },
    )
    return data


def load_provider_example(path: Optional[Path] = None) -> dict[str, Any]:
    p = path or (PKG_ROOT / "config" / "providers.example.yaml")
    return load_yaml(p)


def llm_from_settings(settings: Optional[AppSettings] = None) -> LLMSettings:
    s = settings or AppSettings()
    return LLMSettings(
        base_url=s.masld_llm_base_url,
        api_key_env="MASLD_LLM_API_KEY",
        model=s.masld_llm_model,
        timeout=s.masld_llm_timeout,
        temperature=s.masld_llm_temperature,
    )


def resolve_api_key(api_key_env: str = "MASLD_LLM_API_KEY") -> Optional[str]:
    return os.environ.get(api_key_env) or AppSettings().masld_llm_api_key
