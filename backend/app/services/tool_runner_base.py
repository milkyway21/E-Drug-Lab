"""工具运行器基类。

所有依赖 conda 环境的工具 runner（DiffDynamic / DiffGUI / GLARE / TAME-VS /
DrugClip）共享同一套执行逻辑：在指定 conda 环境内跑脚本、统一返回结构、统一
环境探测。各 runner 只需声明 ``conda_env`` 与 ``root``，调用 ``self._run`` 即可。

设计原则（见 CLAUDE.md）：
- 模型层 = 纯 IO 边界，runner 只做"调用 + 收集输出"，不掺流程逻辑。
- 保留各工具原 ``*_docker.py`` 作为 Windows/Docker 备用，默认走 conda。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from app.services.conda_runner import conda_env_exists, conda_run_json

logger = logging.getLogger(__name__)


class CondaToolRunner:
    """conda 工具运行器基类。

    子类需设置 ``conda_env`` 与 ``root``（工具仓库根目录）。
    """

    conda_env: str = ""
    root: Optional[Path] = None

    def __init__(self, conda_env: str, root: str | Path):
        self.conda_env = conda_env
        self.root = Path(root).resolve()

    def _run(
        self,
        args: list[str],
        *,
        cwd: Optional[str | Path] = None,
        timeout: int = 3600,
        extra_env: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """在 conda 环境内执行命令，返回统一结构。"""
        work_dir = str(cwd) if cwd else (str(self.root) if self.root else None)
        logger.info("[%s] conda run %s (cwd=%s)", self.conda_env, " ".join(args), work_dir)
        return conda_run_json(
            self.conda_env,
            args,
            cwd=work_dir,
            timeout=timeout,
            extra_env=extra_env,
        )

    def env_status(self) -> dict[str, Any]:
        """探测 conda 环境与工具根目录是否就绪。"""
        return {
            "conda_env": self.conda_env,
            "conda_env_exists": conda_env_exists(self.conda_env) if self.conda_env else False,
            "root": str(self.root) if self.root else None,
            "root_exists": bool(self.root and self.root.is_dir()),
        }
