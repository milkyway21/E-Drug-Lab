"""Run commands inside a conda environment.

统一 conda 调用层：所有需要 conda 环境的工具（DiffDynamic / DiffGUI / GLARE /
TAME-VS / DrugClip）都通过本模块执行子进程，避免每个 runner 各自拼 conda 命令。

conda 可执行文件路径解析顺序：
1. 环境变量 ``CONDA_EXE``（conda 激活时自动设置）
2. 配置项 ``tool_paths.conda_exe``（见 config.py，启动时由 ``set_conda_exe`` 注入）
3. 常见安装路径 ``~/anaconda3/bin/conda`` 等
4. ``conda``（依赖 PATH）
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Optional

# 额外的候选 conda 路径，覆盖本机常见安装位置。
_CONDA_CANDIDATES: tuple[str, ...] = (
    os.path.expanduser("~/anaconda3/bin/conda"),
    os.path.expanduser("~/miniconda3/bin/conda"),
    "/home/user/anaconda3/bin/conda",
    "/opt/conda/bin/conda",
)

# 配置项覆盖入口：由 config.py 在启动时通过 set_conda_exe 设置。
_CONFIG_CONDA_EXE: Optional[str] = None


def set_conda_exe(path: Optional[str]) -> None:
    """由 Settings 初始化调用，注入配置中指定的 conda 路径。"""
    global _CONFIG_CONDA_EXE
    _CONFIG_CONDA_EXE = path or None


def find_conda() -> str:
    """返回可用的 conda 可执行文件路径。"""
    for candidate in (
        os.environ.get("CONDA_EXE"),
        _CONFIG_CONDA_EXE,
        *_CONDA_CANDIDATES,
    ):
        if candidate and os.path.isfile(candidate):
            return candidate
    return "conda"


def _env_selector(env_name: str) -> list[str]:
    """根据 env_name 是名字还是路径，返回 ``-n`` 或 ``-p`` 参数。

    新建环境一律建到数据盘（见 CLAUDE.md 磁盘策略），按路径用 ``-p``；
    旧环境用名字，按 ``-n``。
    """
    if os.path.isabs(env_name) or os.sep in env_name:
        return ["-p", env_name]
    return ["-n", env_name]


def conda_run(
    env_name: str,
    args: list[str],
    cwd: Optional[str | Path] = None,
    timeout: Optional[int] = None,
    extra_env: Optional[dict[str, str]] = None,
    check: bool = False,
) -> subprocess.CompletedProcess:
    """在指定 conda 环境内运行命令。

    ``env_name`` 既可以是环境名（``-n``），也可以是环境路径（``-p``，用于数据盘上的环境）。
    使用 ``conda run --no-capture-output`` 以便子进程 stdout/stderr 实时透传。
    """
    conda = find_conda()
    cmd = [conda, "run", "--no-capture-output", *_env_selector(env_name), *args]
    env = os.environ.copy()
    # 规避 diffgui_new 里 protobuf 4.x 与 tensorboard _pb2 的不兼容。
    env.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        timeout=timeout,
        capture_output=True,
        text=True,
        env=env,
        check=check,
    )


def conda_run_json(
    env_name: str,
    args: list[str],
    cwd: Optional[str | Path] = None,
    timeout: Optional[int] = None,
    extra_env: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """运行命令并以统一结构返回结果（不抛异常）。"""
    proc = conda_run(env_name, args, cwd=cwd, timeout=timeout, extra_env=extra_env)
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:] if proc.stdout else "",
        "stderr": proc.stderr[-4000:] if proc.stderr else "",
    }


def conda_env_exists(env_name: str) -> bool:
    """检测某 conda 环境是否存在（支持名字与路径）。"""
    conda = find_conda()
    # 路径形式：直接看目录是否含 python 可执行文件。
    if os.path.isabs(env_name) or os.sep in env_name:
        p = Path(env_name)
        return p.is_dir() and any((p / "bin" / py).is_file() for py in ("python", "python3"))
    try:
        proc = subprocess.run(
            [conda, "env", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            return False
        import json

        data = json.loads(proc.stdout)
        envs = data.get("envs", [])
        names = {Path(e).name for e in envs}
        return env_name in names
    except Exception:
        return False
