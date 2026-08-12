"""合成数据单测：checkpoint_io / coverage / schema / mask 语义（不依赖新 Glide SP）。"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch

from app.pipelines.vav1_rl import checkpoint_io as ckio


def test_coverage_and_enforce():
    recs = [
        {"glide_mask": 1, "md_mask": 0, "physchem": [0.0] * 3},
        {"glide_mask": 0, "md_mask": 1, "physchem": [0.0] * 3},
        {"glide_mask": 0, "md_mask": 0},
    ]
    cov = ckio.compute_coverage(recs)
    assert cov["n_total"] == 3
    assert cov["n_glide_mask_1"] == 1
    assert abs(cov["glide_coverage"] - 1 / 3) < 1e-9
    assert cov["n_md_mask_1"] == 1
    # ginl_pc_gl_md with zero MD must fail
    with pytest.raises(RuntimeError):
        ckio.enforce_coverage(
            {"n_md_mask_1": 0, "md_coverage": 0.0, "glide_coverage": 1.0},
            architecture="ginl_pc_gl_md",
        )


def test_dump_and_load_checkpoint_roundtrip(tmp_path: Path):
    path = tmp_path / "toy.pt"
    schema = ckio.build_feature_schema(
        physchem={"columns": ["a", "b"], "mean": [0.0, 1.0], "std": [1.0, 1.0], "dim": 2},
        glide={"version": "glide_v1", "dim": 16, "mean": [0.0] * 16, "std": [1.0] * 16,
               "score_columns": [], "ifp_columns": []},
    )
    state = {"0": {"out.weight": torch.zeros(2, 4)}}
    payload = ckio.dump_ckpt_payload(
        state=state,
        args={"architecture": "ginl_pc_gl", "fusion_type": "learnable_gate"},
        encoder_type="ginl_pc_gl",
        feature_schema=schema,
        parent_checkpoint="/tmp/prev.pt",
        parent_sha256="abc",
        coverage={"glide_coverage": 0.5},
    )
    torch.save(payload, path)
    loaded = ckio.load_checkpoint_file(path)
    assert loaded["has_feature_schema"]
    assert not loaded["legacy_mode"]
    assert loaded["sha256"]
    assert loaded["ckpt"]["feature_schema"]["physchem"]["dim"] == 2
    sc = ckio.scaler_from_schema_block(loaded["ckpt"]["feature_schema"]["physchem"])
    assert sc is not None
    z = sc.transform(np.asarray([[0.0, 1.0]], dtype=float))
    assert z.shape == (1, 2)


def test_load_state_dict_strictly_critical():
    class Tiny(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.out = torch.nn.Linear(4, 2)
            self.gl_mlp = torch.nn.Linear(2, 2)

    m = Tiny()
    bad = {"out.weight": torch.zeros_like(m.out.weight), "out.bias": torch.zeros_like(m.out.bias)}
    # missing gl_mlp → critical
    with pytest.raises(RuntimeError):
        ckio.load_state_dict_strictly(m, bad)


def test_load_missing_file():
    with pytest.raises(FileNotFoundError):
        ckio.load_checkpoint_file("/tmp/definitely_not_a_ckpt_allin_xyz.pt")


def test_gated_add_mask_zero_no_effect():
    """纯张量级：mask=0 时改变 h_mod 不影响输出（模拟 _gated_add 语义）。"""
    x = torch.randn(3, 8)
    h1 = torch.randn(3, 8)
    h2 = h1 + 10.0
    m = torch.tensor([0.0, 0.0, 0.0])
    out1 = x + 0.1 * (h1 * m.view(-1, 1))
    out2 = x + 0.1 * (h2 * m.view(-1, 1))
    assert torch.allclose(out1, out2)


def test_md_reward_shaping_only_when_mask():
    adv = torch.ones(4)
    m = torch.tensor([1.0, 0.0, 1.0, 0.0])
    r = torch.tensor([0.5, 0.9, -0.5, 0.9])
    eta = 0.2
    shaped = adv * (1.0 + eta * r * m)
    assert abs(float(shaped[0]) - 1.1) < 1e-6
    assert abs(float(shaped[1]) - 1.0) < 1e-6  # mask=0 → 无 shaping
    assert abs(float(shaped[2]) - 0.9) < 1e-6
