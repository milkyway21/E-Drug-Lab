"""GLARE GNN+GRPO 适配器：通过 conda 子进程在 diffgui_new env 调原版 GLARE。

主进程（edrug env）不 import torch_geometric/captum/GLARE，避免环境冲突。
train/query 各写临时 JSON、调 glare_gnn_cli.py 子进程、解析 stdout 最后一行 JSON。

原版 GLARE（third_party/GLARE）提供 GIN+ECFP encoder + GRPO 策略 + Ensemble 不确定性，
超参对齐用户规格：ECFP r=2 nBits=1024 / Adam lr=3e-4 / batch=64 / infer=512 / epochs=50 / hidden=1024。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from app.services.conda_runner import conda_run

logger = logging.getLogger(__name__)

GLARE_CONDA_ENV = "diffgui_new"
CLI_MODULE = "app.pipelines.vav1_rl.glare_gnn_cli"


def _run_cli(args: list[str], timeout: int = 7200) -> dict:
    """调 glare_gnn_cli，返回 stdout 最后一行 JSON 解析结果。"""
    proc = conda_run(GLARE_CONDA_ENV, ["python", "-m", CLI_MODULE, *args], timeout=timeout)
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout)[-2000:]}
    # 取最后一行 JSON
    lines = [ln.strip() for ln in proc.stdout.strip().splitlines() if ln.strip()]
    for line in reversed(lines):
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {"ok": False, "error": "no JSON in stdout", "stdout": proc.stdout[-2000:]}


def train(
    checkpoint_path: str,
    train_smiles: list[str],
    train_labels: list[int],
    sample_weights: Optional[list[float]] = None,
    *,
    molecule_ids: Optional[list[str]] = None,
    prev_checkpoint: Optional[str] = None,
    epochs: int = 50,
    ensemble_size: int = 3,
    lr: float = 3e-4,
    grpo_epsilon: float = 0.2,
    grpo_beta: float = 0.01,
    grpo_lambda: float = 0.07,
    l2_lambda: float = 3e-4,
    weight_decay: float = 0.0,
    batch_size: int = 64,
    strategy: str = "grpo",
    disable_ig: bool = False,
    architecture: str = "ginl",
    beta_pc: float = 0.1,
    beta_gl: float = 0.1,
    beta_md: float = 0.1,
    md_adv_eta: float = 0.0,
) -> dict:
    """GNN+GRPO 训练（子进程 diffgui_new）。数据写临时 JSON。支持自定义超参。"""
    import tempfile
    ids = molecule_ids or [None] * len(train_smiles)
    data = []
    for s, lb, w, mid in zip(
        train_smiles, train_labels, sample_weights or [1.0] * len(train_smiles), ids
    ):
        row = {"smiles": s, "label": int(lb), "weight": float(w)}
        if mid is not None:
            row["molecule_id"] = str(mid)
        data.append(row)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        data_path = f.name
    args = [
        "train", "--ckpt", checkpoint_path, "--data", data_path,
        "--epochs", str(epochs), "--ensemble", str(ensemble_size),
        "--lr", str(lr), "--grpo_epsilon", str(grpo_epsilon),
        "--grpo_beta", str(grpo_beta), "--grpo_lambda", str(grpo_lambda),
        "--l2_lambda", str(l2_lambda), "--weight_decay", str(weight_decay),
        "--batch_size", str(batch_size), "--strategy", strategy,
        "--architecture", architecture,
        "--beta_pc", str(beta_pc), "--beta_gl", str(beta_gl), "--beta_md", str(beta_md),
        "--md_adv_eta", str(md_adv_eta),
    ]
    if prev_checkpoint:
        args.extend(["--prev", prev_checkpoint])
    if disable_ig:
        args.append("--disable-ig")
    res = _run_cli(args)
    try:
        Path(data_path).unlink()
    except Exception:
        pass
    return res


def query(
    checkpoint_path: str,
    screen_smiles: list[str],
    *,
    ensemble_size: int = 3,
) -> dict:
    """GNN+GRPO 排序（子进程 diffgui_new）。"""
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(screen_smiles, f)
        smi_path = f.name
    args = ["query", "--ckpt", checkpoint_path, "--smiles", smi_path, "--ensemble", str(ensemble_size)]
    res = _run_cli(args, timeout=3600)
    try:
        Path(smi_path).unlink()
    except Exception:
        pass
    return res


def smoke_test() -> dict:
    """快速检查 diffgui_new env 是否能 import GLARE（仅 import，不加载模型）。"""
    script = (
        "import sys; sys.path.insert(0,'/data/ye/e-drug-lab/backend'); "
        "from app.pipelines.vav1_rl.glare_gnn_cli import _setup; "
        "print('GLARE_IMPORT_OK')"
    )
    proc = conda_run(GLARE_CONDA_ENV, ["python", "-c", script], timeout=15)
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout)[-600:]}
    return {"ok": True, "env": GLARE_CONDA_ENV}
