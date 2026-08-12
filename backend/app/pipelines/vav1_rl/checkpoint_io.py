"""Checkpoint / feature_schema / coverage 工具（不依赖 GLARE 图网络）。

供 glare_gnn_cli 与单测共用；禁止静默吞异常。
"""
from __future__ import annotations

import hashlib
import json
import warnings
from pathlib import Path
from typing import Any, Optional


FEATURE_SCHEMA_VERSION = 2

# 关键层名片段：缺失则判定 critical
_CRITICAL_KEY_SUBSTR = (
    "atom_embedding",
    "graph_conv",
    "x_fc",
    "fp_fc",
    "out.",
    "pc_mlp",
    "gl_mlp",
    "md_mlp",
    "gate_pc",
    "gate_gl",
    "gate_md",
    "alpha_head",
)


def verify_architecture(ckpt_args: dict[str, Any], requested_arch: str) -> None:
    """校验 checkpoint 的 architecture 与请求的 architecture 一致。

    防止 *_md_* 目录用 ginl_pc_gl checkpoint 这种错位。
    """
    ckpt_arch = str(ckpt_args.get("architecture", "")).lower()
    req_arch = str(requested_arch or "").lower()
    if not ckpt_arch:
        warnings.warn("[arch_verify] checkpoint has no architecture field; skipping", stacklevel=2)
        return
    if not req_arch:
        return
    if ckpt_arch != req_arch:
        raise RuntimeError(
            f"[arch_verify] checkpoint architecture '{ckpt_arch}' != requested '{req_arch}'. "
            f"Checkpoint and output directory architecture must match."
        )


def file_sha256(path: Path | str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def build_feature_schema(
    *,
    physchem: Optional[dict[str, Any]] = None,
    glide: Optional[dict[str, Any]] = None,
    md: Optional[dict[str, Any]] = None,
    target_id: Optional[str] = None,
    profile_path: Optional[str] = None,
) -> dict[str, Any]:
    schema = {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "target_id": target_id,
        "profile_path": profile_path,
        "physchem": physchem,
        "glide": glide,
        "md": md,
    }
    schema["schema_hash"] = schema_hash(schema)
    return schema


def schema_hash(schema: dict[str, Any]) -> str:
    """Return a stable hash excluding the hash field itself."""
    payload = {
        key: value
        for key, value in schema.items()
        if key not in {"schema_hash", "profile_path"}
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def physchem_schema_from_scaler(scaler: Any, columns: list[str]) -> dict[str, Any]:
    return {
        "columns": list(columns),
        "mean": [float(x) for x in scaler.mean],
        "std": [float(x) for x in scaler.std],
        "dim": int(len(columns)),
    }


def glide_schema_from_store(store: Any) -> dict[str, Any]:
    if hasattr(store, "schema"):
        return store.schema()
    from app.pipelines.vav1_rl.glide_features import GLIDE_SCORE_COLS, IFP_COLS, GLIDE_DIM
    return {
        "version": "glide_v1",
        "score_columns": list(GLIDE_SCORE_COLS),
        "ifp_columns": list(IFP_COLS),
        "mean": [float(x) for x in store.mean],
        "std": [float(x) for x in store.std],
        "dim": int(GLIDE_DIM),
    }


def md_schema_from_store(store: Any) -> dict[str, Any]:
    names = list(store.spec.get("names", []))
    scaler = getattr(store, "scaler", {}) or {}
    mean = scaler.get("mean")
    std = scaler.get("std")
    return {
        "columns": names,
        "mean": [float(x) for x in mean] if mean is not None else None,
        "std": [float(x) for x in std] if std is not None else None,
        "dim": int(store.dim),
        "key_residues": list(store.spec.get("key_residues", [])),
    }


def compute_coverage(records: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(records)
    n_gl = sum(1 for r in records if int(r.get("glide_mask", 0) or 0) == 1)
    n_md = sum(1 for r in records if int(r.get("md_mask", 0) or 0) == 1)
    n_pc = sum(1 for r in records if r.get("physchem") is not None)
    return {
        "n_total": n,
        "n_valid_physchem": n_pc,
        "n_glide_mask_1": n_gl,
        "glide_coverage": (n_gl / n) if n else 0.0,
        "n_md_mask_1": n_md,
        "md_coverage": (n_md / n) if n else 0.0,
    }


def enforce_coverage(
    coverage: dict[str, Any],
    *,
    architecture: str,
    min_glide_coverage: float = 0.0,
    min_md_coverage: float = 0.0,
    fail_on_low_coverage: bool = False,
) -> None:
    arch = (architecture or "").lower()
    g = float(coverage.get("glide_coverage", 0.0))
    m = float(coverage.get("md_coverage", 0.0))
    if arch in ("ginl_pc_gl", "ginl_pc_gl_md", "ginl_pc_gl_mdprior") and min_glide_coverage > 0 and g < min_glide_coverage:
        msg = f"[coverage] Glide coverage {g:.3f} < min_glide_coverage {min_glide_coverage}"
        if fail_on_low_coverage:
            raise RuntimeError(msg)
        warnings.warn(msg, stacklevel=2)
    if arch == "ginl_pc_gl_md":
        if coverage.get("n_md_mask_1", 0) == 0:
            raise RuntimeError("[coverage] ginl_pc_gl_md requires md_mask=1 on at least one sample")
        if min_md_coverage > 0 and m < min_md_coverage:
            msg = f"[coverage] MD coverage {m:.3f} < min_md_coverage {min_md_coverage}"
            if fail_on_low_coverage:
                raise RuntimeError(msg)
            warnings.warn(msg, stacklevel=2)
    # ginl_pc_gl_mdprior 不要求 md_mask=1（MD 通过 q_i gate 传播，不需要 per-molecule MD）


def _is_critical_missing(key: str) -> bool:
    return any(s in key for s in _CRITICAL_KEY_SUBSTR)


def load_state_dict_strictly(
    module: Any,
    state_dict: dict[str, Any],
    *,
    allow_missing_prefixes: Optional[tuple[str, ...]] = None,
) -> dict[str, Any]:
    """加载并返回 missing/unexpected；关键层缺失则抛错。"""
    allow_missing_prefixes = allow_missing_prefixes or ()
    incompatible = module.load_state_dict(state_dict, strict=False)
    missing = list(getattr(incompatible, "missing_keys", []) or [])
    unexpected = list(getattr(incompatible, "unexpected_keys", []) or [])
    critical = [
        k for k in missing
        if _is_critical_missing(k) and not any(k.startswith(p) for p in allow_missing_prefixes)
    ]
    report = {
        "missing_keys": missing,
        "unexpected_keys": unexpected,
        "critical_missing": critical,
        "ok": len(critical) == 0,
    }
    if critical:
        raise RuntimeError(
            f"checkpoint critical missing keys: {critical[:20]}"
            + (f" ... (+{len(critical)-20})" if len(critical) > 20 else "")
        )
    return report


def load_checkpoint_file(
    path: Path | str,
    *,
    allowed_roots: Optional[tuple[Path | str, ...]] = None,
    allow_legacy_pickle: bool = False,
) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"checkpoint not found: {path}")
    path = path.resolve()
    if allowed_roots:
        roots = [Path(root).expanduser().resolve() for root in allowed_roots]
        if not any(path == root or root in path.parents for root in roots):
            raise PermissionError(f"checkpoint is outside allowed roots: {path}")
    import torch

    unsafe_pickle_used = False
    try:
        ckpt = torch.load(path, map_location="cpu", weights_only=True)
    except TypeError as exc:
        if not allow_legacy_pickle:
            raise RuntimeError(
                "this PyTorch version cannot perform safe checkpoint loading; "
                "upgrade PyTorch or explicitly pass allow_legacy_pickle=True for "
                "a trusted legacy VAV1 checkpoint"
            ) from exc
        warnings.warn(
            f"[legacy_checkpoint] using explicitly enabled unsafe pickle load for {path}",
            stacklevel=2,
        )
        unsafe_pickle_used = True
        try:
            ckpt = torch.load(path, map_location="cpu", weights_only=False)
        except TypeError:
            ckpt = torch.load(path, map_location="cpu")
    except Exception as exc:
        if not allow_legacy_pickle:
            raise RuntimeError(
                f"safe checkpoint loading failed for {path}; refusing unsafe pickle "
                "fallback. Pass allow_legacy_pickle=True only for a trusted legacy "
                "VAV1 checkpoint"
            ) from exc
        warnings.warn(
            f"[legacy_checkpoint] using explicitly enabled unsafe pickle load for {path}: {exc}",
            stacklevel=2,
        )
        unsafe_pickle_used = True
        ckpt = torch.load(path, map_location="cpu", weights_only=False)
    if not isinstance(ckpt, dict):
        raise RuntimeError(f"checkpoint is not a dict: {path}")
    if unsafe_pickle_used:
        checkpoint_target = str(
            ckpt.get("target_id")
            or (ckpt.get("args") or {}).get("target_id")
            or "vav1"
        ).lower()
        if ckpt.get("feature_schema") is not None or checkpoint_target != "vav1":
            raise RuntimeError(
                "unsafe pickle loading is restricted to legacy VAV1 checkpoints "
                "without feature_schema"
            )
    return {
        "ckpt": ckpt,
        "path": str(path),
        "sha256": file_sha256(path),
        "has_feature_schema": "feature_schema" in ckpt and ckpt["feature_schema"] is not None,
        "legacy_mode": "feature_schema" not in ckpt or ckpt.get("feature_schema") is None,
        "unsafe_pickle_used": unsafe_pickle_used,
    }


def validate_target_schema(
    checkpoint: dict[str, Any],
    *,
    target_id: Optional[str] = None,
    feature_schema: Optional[dict[str, Any]] = None,
) -> None:
    """Reject target/schema mismatches before model construction."""
    saved = checkpoint.get("feature_schema") or {}
    saved_top_target = checkpoint.get("target_id")
    if target_id and saved_top_target and str(target_id) != str(saved_top_target):
        raise RuntimeError(
            f"checkpoint target '{saved_top_target}' != requested target '{target_id}'"
        )
    if not saved:
        return
    saved_target = saved.get("target_id")
    if target_id and saved_target and str(target_id) != str(saved_target):
        raise RuntimeError(
            f"checkpoint target '{saved_target}' != requested target '{target_id}'"
        )
    expected_hash = saved.get("schema_hash")
    if expected_hash and schema_hash(saved) != expected_hash:
        raise RuntimeError("checkpoint feature_schema hash is invalid")
    if feature_schema and not expected_hash:
        raise RuntimeError("checkpoint feature_schema has no schema_hash")
    if feature_schema and expected_hash:
        actual_hash = feature_schema.get("schema_hash") or schema_hash(feature_schema)
        if actual_hash != expected_hash:
            raise RuntimeError(
                f"feature schema mismatch: checkpoint={expected_hash}, current={actual_hash}"
            )


def scaler_from_schema_block(block: Optional[dict[str, Any]]) -> Optional[Any]:
    """从 schema 块重建 PhysChemScaler 兼容对象（mean/std arrays）。"""
    if not block or block.get("mean") is None or block.get("std") is None:
        return None
    import numpy as np
    from app.pipelines.vav1_rl.physchem_101 import PhysChemScaler

    mean = np.asarray(block["mean"], dtype=np.float64)
    std = np.asarray(block["std"], dtype=np.float64)
    cols = block.get("columns") or [f"f{i}" for i in range(len(mean))]
    return PhysChemScaler(mean=mean, std=std, columns=list(cols))


def dump_ckpt_payload(
    *,
    state: dict[str, Any],
    args: dict[str, Any],
    encoder_type: str,
    feature_schema: Optional[dict[str, Any]] = None,
    parent_checkpoint: Optional[str] = None,
    parent_sha256: Optional[str] = None,
    coverage: Optional[dict[str, Any]] = None,
    target_id: Optional[str] = None,
    profile_path: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "state": state,
        "args": args,
        "encoder_type": encoder_type,
        "feature_schema": feature_schema,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "parent_checkpoint": parent_checkpoint,
        "parent_sha256": parent_sha256,
        "coverage": coverage,
        "target_id": target_id,
        "profile_path": profile_path,
    }
