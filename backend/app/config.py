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
    api_key: Optional[str] = Field(default=None, description="薛定谔 API 密钥（可选，远程 API 用）")
    base_url: str = Field(default="https://api.schrodinger.com/v1")
    timeout: int = Field(default=300)
    # 本地安装（2023-3）subprocess 调用相关
    use_local: bool = Field(default=True, description="优先用本地安装而非远程 API")
    install_path: str = Field(default="/opt/schrodinger2023-3", description="薛定谉本地安装路径")
    ph: float = Field(default=7.2, description="配体/蛋白质子化 pH（LigPrep/PrepWizard）")
    ph_threshold: float = Field(default=0.2, description="pH 容差")
    host: str = Field(default="localhost", description="Schrodinger hosts 文件中的 host 名")
    class Config:
        env_prefix = "SCHRODINGER_"
        extra = "ignore"


class DrugClipSettings(BaseSettings):
    # 运行时选择：conda（默认，本地 conda 环境）或 docker（Windows/WSL 备用）
    runtime: str = Field(default="conda", description="运行后端：conda | docker")
    conda_env: str = Field(default="drugclip", description="DrugClip 本地 conda 环境名")
    service_url: str = Field(default="http://localhost:8500", description="DrugCLIP 服务地址（conda 直跑 uvicorn 或 docker 容器）")
    timeout: int = Field(default=600)
    # Docker/WSL 备用字段（Windows 侧适配保留）
    image_name: str = Field(default="drugclip-api:latest")
    wsl_exe: str = Field(default=r"C:\Windows\System32\wsl.exe")
    wsl_distro: Optional[str] = Field(default="eDrugUbuntu")
    package_path: str = Field(default="deliverables/drugclip-package")
    output_dir: str = Field(default="outputs/drugclip")
    class Config:
        env_prefix = "DRUGCLIP_"
        extra = "ignore"


class TameVSSettings(BaseSettings):
    # 运行时选择：conda（默认，本地 conda 环境）或 docker（Windows/WSL 备用）
    runtime: str = Field(default="conda", description="运行后端：conda | docker")
    conda_env: str = Field(default="/data/ye/envs/TAME_VS2", description="TAME-VS 本地 conda 环境路径（数据盘）")
    api_key: Optional[str] = Field(default=None, description="TAME-VS API 密钥（可选）")
    base_url: str = Field(default="https://api.tamevs.org/v1")
    timeout: int = Field(default=600)
    repo_path: str = Field(default="tools/Target-driven-ML-enabled-VS")
    # Docker/WSL 备用字段（Windows 侧适配保留）
    image_name: str = Field(default="edrug-lab/tame-vs:latest")
    wsl_exe: str = Field(default=r"C:\Windows\System32\wsl.exe")
    wsl_distro: Optional[str] = Field(default=None)
    output_dir: str = Field(default="outputs/tame-vs")
    package_path: str = Field(default="deliverables/target-driven-vs-package")
    service_url: str = Field(default="http://localhost:8000")
    chembl_db: str = Field(default="/data/ye/tame-vs-data/chembl/chembl_35.db", description="ChEMBL SQLite 数据库路径")
    class Config:
        env_prefix = "TAME_VS_"
        extra = "ignore"


class DiffDynamicSettings(BaseSettings):
    # 运行时选择：local（默认，本地 conda 调用 /data/ye/DiffDynamic）或 remote（远程 API）
    runtime: str = Field(default="local", description="运行后端：local | remote")
    conda_env: str = Field(default="diffdynamic", description="DiffDynamic 本地 conda 环境名")
    root: str = Field(default="/data/ye/DiffDynamic", description="DiffDynamic 仓库根目录")
    sampling_config: str = Field(default="configs/sampling.yml", description="采样配置文件（相对 root）")
    protein_root: str = Field(
        default="data/crossdocked_v1.1_rmsd1.0_pocket10",
        description="蛋白数据根目录（相对 root，用于评估/提取）",
    )
    default_device: str = Field(default="cuda:0", description="默认 GPU 设备")
    outputs_dir: str = Field(default="outputs/diffdynamic", description="输出目录（相对仓库）")
    vina_timeout: int = Field(default=20, ge=1, le=600, description="Vina 对接超时（秒）")
    # 远程 API 备用字段
    api_key: Optional[str] = Field(default=None, description="DiffDynamic API 密钥（可选，remote 模式用）")
    base_url: str = Field(default="https://api.diffdynamic.org/v1")
    timeout: int = Field(default=900)
    class Config:
        env_prefix = "DIFFDYNAMIC_"
        extra = "ignore"


class ToolPathsSettings(BaseSettings):
    autodock_vina: Optional[str] = Field(default=None, description="AutoDock Vina 可执行文件路径（可选）")
    fpocket: Optional[str] = Field(default=None, description="Fpocket 可执行文件路径（可选）")
    gromacs: Optional[str] = Field(default=None)
    openmm: Optional[str] = Field(default=None)
    rdkit_data: Optional[str] = Field(default=None, description="RDKit 数据目录（可选）")
    conda_exe: Optional[str] = Field(default=None, description="conda 可执行文件路径（留空则自动发现）")
    class Config:
        env_prefix = "TOOL_"
        extra = "ignore"


class CelerySettings(BaseSettings):
    broker_url: str = Field(default="redis://localhost:6379/0")
    result_backend: str = Field(default="redis://localhost:6379/1")
    task_serializer: str = Field(default="json")
    result_serializer: str = Field(default="json")
    timezone: str = Field(default="Asia/Shanghai")
    class Config:
        env_prefix = "CELERY_"
        extra = "ignore"


class AdmetSettings(BaseSettings):
    enabled: bool = Field(default=True, description="是否启用 ADMET-AI 预测")
    model_timeout: int = Field(default=60, description="模型推理超时（秒）")
    batch_size: int = Field(default=32, ge=1, le=512, description="批量预测大小")
    class Config:
        env_prefix = "ADMET_"
        extra = "ignore"


class DiffGuiSettings(BaseSettings):
    root: str = Field(default="/data/ye/diffgui")
    conda_env: str = Field(default="diffgui_new")
    sample_config: str = Field(default="configs/sample/sample.yml")
    default_device: str = Field(default="cuda:0")
    outputs_dir: str = Field(default="outputs/rl_rounds")
    class Config:
        env_prefix = "DIFFGUI_"
        extra = "ignore"


class GlareSettings(BaseSettings):
    root: str = Field(default="/data/ye/diffgui")
    config_path: str = Field(default="glare_selector/glare_config.yaml")
    db_path: str = Field(default="vav1_molecular_glue_screening.db")
    seed_activity_file: str = Field(default="data/seed/seed_activity_data.xlsx")
    conda_env: str = Field(default="diffgui_new")
    # RL 轮次输出根目录；留空则复用 rl_round_service.rounds_base_dir()（backend/outputs/rl_rounds）
    outputs_dir: Optional[str] = Field(default=None, description="GLARE/RL 输出根目录（留空则用规范 rl_rounds 路径）")
    class Config:
        env_prefix = "GLARE_"
        extra = "ignore"


class Settings(BaseSettings):
    app_name: str = "e-drug lab"
    debug: bool = Field(default=False, validation_alias=AliasChoices("APP_DEBUG", "debug"))
    host: str = Field(default="0.0.0.0", validation_alias=AliasChoices("APP_HOST", "host"))
    port: int = Field(default=8000, ge=1, le=65535, validation_alias=AliasChoices("APP_PORT", "port"))
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = Field(default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:3003,http://127.0.0.1:3003")
    database: DatabaseSettings
    schrodinger: SchrodingerSettings
    drugclip: DrugClipSettings
    tame_vs: TameVSSettings
    diffdynamic: DiffDynamicSettings
    diffgui: DiffGuiSettings = DiffGuiSettings()
    glare: GlareSettings = GlareSettings()
    tool_paths: ToolPathsSettings
    celery: CelerySettings
    admet: AdmetSettings = AdmetSettings()
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$", validation_alias=AliasChoices("APP_LOG_LEVEL", "log_level"))
    log_format: str = Field(default="json", pattern="^(json|text)$", validation_alias=AliasChoices("APP_LOG_FORMAT", "log_format"))
    sdf_directory: Optional[str] = Field(
        default=None,
        description="默认 SDF 库目录（留空则用 molecules/sdf）",
        validation_alias=AliasChoices("SDF_DIRECTORY", "sdf_directory"),
    )

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
        # 规避裸 env 变量与嵌套设置字段同名导致的 JSON 解码失败：
        # 例如薛定谔套装安装路径 ``SCHRODINGER=/opt/schrodinger2023-3/`` 会被
        # pydantic-settings 当作 ``schrodinger`` 嵌套字段的裸值去 json.loads。
        # 这些裸变量 backend 不消费（薛定谔 API 配置走 SCHRODINGER__*），构造时临时屏蔽。
        _colliding_bare_env = ("SCHRODINGER",)
        _saved = {k: os.environ.pop(k) for k in _colliding_bare_env if k in os.environ}
        try:
            settings = Settings()
        finally:
            os.environ.update(_saved)
        # 注入配置指定的 conda 路径到统一调用层。
        from app.services.conda_runner import set_conda_exe

        set_conda_exe(settings.tool_paths.conda_exe)
    return settings
