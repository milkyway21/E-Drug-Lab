"""DiffDynamic runner unit tests (mock conda, no GPU)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from app.config import DiffDynamicSettings
from app.services.diffdynamic_runner import DiffDynamicRunner


@pytest.fixture
def runner(tmp_path: Path) -> DiffDynamicRunner:
    root = tmp_path / "DiffDynamic"
    root.mkdir()
    (root / "configs").mkdir()
    sampling = root / "configs" / "sampling.yml"
    sampling.write_text(
        yaml.safe_dump({"sample": {"mode": "dynamic", "dynamic": {"large_step": {"batch_size": 100}}}}),
        encoding="utf-8",
    )
    for script in (
        "batch_sampleandeval_parallel.py",
        "run_prudent_generations.py",
        "evaluate_pocket_quality.py",
        "extract_pt_to_sdf_excel.py",
    ):
        (root / script).write_text("# stub\n", encoding="utf-8")
    (root / "data" / "crossdocked").mkdir(parents=True)

    settings = DiffDynamicSettings(
        root=str(root),
        sampling_config="configs/sampling.yml",
        protein_root="data/crossdocked",
        outputs_dir="outputs/diffdynamic",
    )
    return DiffDynamicRunner(settings)


def test_status_reports_scripts(runner: DiffDynamicRunner):
    status = runner.status()
    assert status["root_exists"] is True
    assert status["scripts"]["dynamic"] is True
    assert status["scripts"]["extract"] is True


def test_render_run_config_overrides_batch_size(runner: DiffDynamicRunner, tmp_path: Path):
    out = tmp_path / "run_out"
    cfg_path = runner._render_run_config(mode="dynamic", batch_size=5, output_dir=out)
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert data["sample"]["mode"] == "dynamic"
    assert data["sample"]["dynamic"]["large_step"]["batch_size"] == 5


@patch("app.services.diffdynamic_runner.CondaToolRunner._run")
def test_run_dynamic_builds_expected_command(mock_run, runner: DiffDynamicRunner):
    mock_run.return_value = {"ok": True, "returncode": 0, "stdout": "", "stderr": ""}
    result = runner.run_dynamic(data_id=0, batch_size=5, sample_only=True)
    assert result["ok"] is True
    assert result["data_id"] == 0
    args = mock_run.call_args[0][0]
    assert "--data_ids" in args
    assert "0" in args
    assert "--sample-only" in args


@patch("app.services.diffdynamic_runner.CondaToolRunner._run")
def test_run_custom_requires_protein(mock_run, runner: DiffDynamicRunner):
    result = runner.run_custom(protein_path="/no/such/file.pdb")
    assert result["ok"] is False
    mock_run.assert_not_called()


def test_merge_sdf_files(tmp_path: Path, runner: DiffDynamicRunner):
    a = tmp_path / "a.sdf"
    b = tmp_path / "b.sdf"
    a.write_text("mol1\n$$$$\n", encoding="utf-8")
    b.write_text("mol2\n$$$$\n", encoding="utf-8")
    dest = tmp_path / "merged.sdf"
    runner.merge_sdf_files([a, b], dest)
    text = dest.read_text(encoding="utf-8")
    assert "mol1" in text and "mol2" in text


def test_tool_registry_contains_diffdynamic():
    from app.core.tool_registry import TOOL_REGISTRY

    assert "diffdynamic" in TOOL_REGISTRY
    assert TOOL_REGISTRY["diffdynamic"].api_route == "POST /api/v1/diffdynamic/generate"
