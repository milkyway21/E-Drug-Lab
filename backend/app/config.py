"""
e-drug lab 配置管理
集中式配置，启动时验证，fail fast 原则
"""
import json
import os
from typing import Any, Optional
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings


class DatabaseSettings(BaseSettings):
    url: str = Field(..., description="PostgreSQL 连接字符串")
    pool_size: int = Field(default=10, ge=1, le=50)
    echo: bool = Field(default=False)
    class Config:
        env_prefix = "DATABASE_"


class SchrodingerSettings(BaseSettings):
    api_key: str = Field(..., description="薛定谔 API 密钥")
    base_url: str = Field(default="https://api.schrodinger.com/v1")
    timeout: int = Field(default=300)
    class Config:
        env_prefix = "SCHRODINGER_"


class DrugClipSettings(BaseSettings):
    api_key: str = Field(..., description="DrugClip API 密钥")
    base_url: str = Field(default="https://api.drugclip.com/v1")
    class Config:
        env_prefix = "DRUGCLIP_"


class TameVSSettings(BaseSettings):
    api_key: Optional[str] = Field(default=None, description="TAME-VS API 密钥")
    base_url: str = Field(default="https://api.tamevs.org/v1")
    timeout: int = Field(default=600)
    repo_path: str = Field(default="tools/Target-driven-ML-enabled-VS")
    image_name: str = Field(default="edrug-lab/tame-vs:latest")
    wsl_exe: str = Field(default=r"C:\Windows\System32\wsl.exe")
    wsl_distro: Optional[str] = Field(default=None)
    output_dir: str = Field(default="outputs/tame-vs")
    package_path: str = Field(default="deliverables/target-driven-vs-package")
    service_url: str = Field(default="http://localhost:8000")
    class Config:
        env_prefix = "TAME_VS_"


class DiffDynamicSettings(BaseSettings):
    api_key: str = Field(..., description="DiffDynamic API 密钥")
    base_url: str = Field(default="https://api.diffdynamic.org/v1")
    timeout: int = Field(default=900)
    class Config:
        env_prefix = "DIFFDYNAMIC_"


class ToolPathsSettings(BaseSettings):
    autodock_vina: str = Field(..., description="AutoDock Vina 可执行文件路径")
    fpocket: str = Field(..., description="Fpocket 可执行文件路径")
    gromacs: Optional[str] = Field(default=None)
    openmm: Optional[str] = Field(default=None)
    rdkit_data: str = Field(..., description="RDKit 数据目录")
    class Config:
        env_prefix = "TOOL_"


class CelerySettings(BaseSettings):
    broker_url: str = Field(default="redis://localhost:6379/0")
    result_backend: str = Field(default="redis://localhost:6379/1")
    task_serializer: str = Field(default="json")
    result_serializer: str = Field(default="json")
    timezone: str = Field(default="Asia/Shanghai")
    class Config:
        env_prefix = "CELERY_"


class Settings(BaseSettings):
    app_name: str = "e-drug lab"
    debug: bool = Field(default=False, validation_alias=AliasChoices("APP_DEBUG", "debug"))
    host: str = Field(default="0.0.0.0", validation_alias=AliasChoices("APP_HOST", "host"))
    port: int = Field(default=8000, ge=1, le=65535, validation_alias=AliasChoices("APP_PORT", "port"))
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = Field(default="http://localhost:3000,http://127.0.0.1:3000")
    database: DatabaseSettings
    schrodinger: SchrodingerSettings
    drugclip: DrugClipSettings
    tame_vs: TameVSSettings
    diffdynamic: DiffDynamicSettings
    tool_paths: ToolPathsSettings
    celery: CelerySettings
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$", validation_alias=AliasChoices("APP_LOG_LEVEL", "log_level"))
    log_format: str = Field(default="json", pattern="^(json|text)$", validation_alias=AliasChoices("APP_LOG_FORMAT", "log_format"))

    class Config:
        env_file = ".env"
        env_nested_delimiter = "__"
        extra = "ignore"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _normalize_cors_origins(cls, v: Any) -> str:
        if v is None:
            return "http://localhost:3000,http://127.0.0.1:3000"
        if isinstance(v, list):
            return ",".join(str(x).strip() for x in v if str(x).strip())
        if isinstance(v, str) and not v.strip():
            return "http://localhost:3000,http://127.0.0.1:3000"
        return str(v).strip()

    @property
    def cors_origins_list(self) -> list[str]:
        raw = (self.cors_origins or "").strip()
        if not raw:
            return ["http://localhost:3000", "http://127.0.0.1:3000"]
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if str(x).strip()]
            except json.JSONDecodeError:
                pass
        return [x.strip() for x in raw.split(",") if x.strip()]


settings: Optional[Settings] = None


def get_settings() -> Settings:
    global settings
    if settings is None:
        settings = Settings()
    return settings
