"""Deterministic funnel planner, runner, and weak-model entrypoint tests."""
from __future__ import annotations

import csv
import gzip
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

from masld_agent.funnel.autopilot import autopilot_status, run_autopilot, start_autopilot
from masld_agent.funnel.diffdynamic import prudent_generate, prudent_physchem
from masld_agent.funnel.planner import allocate_resources, plan_campaign, plan_counts
from masld_agent.funnel.runner import preflight_campaign, run_stage, stage_status, validate_stage
from masld_agent.funnel.utilities import inspect_sdf, rank_glide_parents
from masld_agent.hermes_plugin import register


IMPORTER_PATH = Path(__file__).parents[1] / "scripts" / "import_drug_skills.py"
IMPORTER_SPEC = importlib.util.spec_from_file_location("import_drug_skills", IMPORTER_PATH)
assert IMPORTER_SPEC is not None and IMPORTER_SPEC.loader is not None
IMPORTER = importlib.util.module_from_spec(IMPORTER_SPEC)
IMPORTER_SPEC.loader.exec_module(IMPORTER)
FUNNEL_FLOWCHART = IMPORTER.FUNNEL_FLOWCHART
ROOT = IMPORTER.ROOT
_find_skill = IMPORTER._find_skill
_link_skill = IMPORTER._link_skill


def campaign_manifest(tmp_path: Path, *, stages: dict | None = None) -> Path:
    root = tmp_path / "campaign"
    inputs = root / "inputs"
    inputs.mkdir(parents=True)
    assets = {}
    for key, name in (
        ("receptor_pdb", "receptor.pdb"),
        ("reference_ligand_sdf", "ligand.sdf"),
        ("prepwizard_mae", "receptor.maegz"),
        ("grid_zip", "grid.zip"),
    ):
        path = inputs / name
        path.write_text("nonempty\n", encoding="utf-8")
        assets[key] = str(path)
    manifest = inputs / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "campaign_id": "test_campaign",
                "target_id": "TEST",
                "campaign_root": str(root),
                "inputs": assets,
                "stages": stages or {},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


def test_test_profile_matches_requested_smoke_counts():
    plan = plan_counts(2, profile="test")
    assert plan["profile"] == "test"
    assert plan["stage_targets"]["H1A"] == 0
    assert plan["stage_targets"]["H1B"] == 100
    assert plan["stage_targets"]["H3"] == 30
    assert plan["stage_targets"]["H4"] == 5
    assert plan["stage_targets"]["H5"] == 2
    assert plan["stage_targets"]["H8"] == 2


def test_full_profile_is_default_and_matches_three_round_flowchart():
    plan = plan_counts(10)
    assert plan["profile"] == "full"
    assert plan["stage_targets"] == {
        "H0": 1,
        "H1A": 500_000,
        "H1B": 40_000,
        "H2": 1_000,
        "H3": 3_000,
        "H4": 3_000,
        "H5": 500,
        "H6": 130,
        "H7": 40,
        "H8": 20,
        "H9": 10,
        "H10": 10,
    }
    assert plan["rules"]["prudent_analysis_vina_modes"] == "none"
    assert plan["stage_plan"]["H4"]["backend_policy"] == "schrodinger_qikprop_required"


def test_resource_allocation_avoids_busy_or_missing_gpu():
    inventory = {"cpu_jobs": 12, "available_gpu_ids": [1, 4]}
    allocations = allocate_resources(inventory, final_count=3)
    assert allocations["H1B"]["gpu_ids"] == [1, 4]
    assert allocations["H8"]["gpu_ids"] == [1, 4]
    assert allocations["H2"]["cpu_jobs"] == 12


def test_plan_honors_manifest_gpu_allowlist(tmp_path: Path, monkeypatch):
    manifest = campaign_manifest(tmp_path)
    payload = json.loads(manifest.read_text())
    payload["resource_policy"] = {"allowed_gpu_ids": [1, 3]}
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        "masld_agent.funnel.planner.resource_inventory",
        lambda root: {
            "captured_at": "test",
            "cpu_total": 8,
            "cpu_jobs": 6,
            "memory_available_gb": 16,
            "disk_free_gb": 100,
            "gpus": [],
            "available_gpu_ids": [0, 1, 3, 4],
        },
    )
    result = plan_campaign(2, manifest_path=manifest, profile="test")
    assert result["resource_inventory"]["available_gpu_ids"] == [1, 3]
    assert result["resource_allocations"]["H1B"]["gpu_ids"] == [1, 3]
    assert result["resource_allocations"]["H8"]["gpu_ids"] == [1, 3]


def test_plan_writes_counts_and_resource_snapshot(tmp_path: Path, monkeypatch):
    manifest = campaign_manifest(tmp_path)
    monkeypatch.setattr(
        "masld_agent.funnel.planner.resource_inventory",
        lambda root: {
            "captured_at": "test",
            "cpu_total": 8,
            "cpu_jobs": 6,
            "memory_available_gb": 16,
            "disk_free_gb": 100,
            "gpus": [],
            "available_gpu_ids": [],
        },
    )
    result = plan_campaign(2, manifest_path=manifest, profile="test")
    updated = json.loads(manifest.read_text())
    assert Path(result["plan_path"]).is_file()
    assert updated["pipeline_targets"]["H8"] == 2
    assert updated["pipeline_targets"]["H10"] == 0
    assert updated["funnel_profile"]["id"] == "test"
    assert updated["stages"]["H4"]["required_backend_policy"] == (
        "schrodinger_qikprop_required"
    )
    assert updated["stages"]["H3"]["target_count"] == 30


def test_autopilot_preview_reports_every_stage(tmp_path: Path, monkeypatch):
    manifest = campaign_manifest(tmp_path)
    monkeypatch.setattr(
        "masld_agent.funnel.planner.resource_inventory",
        lambda root: {
            "captured_at": "test",
            "cpu_total": 4,
            "cpu_jobs": 3,
            "memory_available_gb": 8,
            "disk_free_gb": 50,
            "gpus": [],
            "available_gpu_ids": [],
        },
    )
    result = run_autopilot(2, manifest_path=manifest, profile="test")
    assert result["status"] == "planned"
    assert result["profile"] == "test"
    assert result["stages_processed"] == 12
    state = autopilot_status(manifest_path=manifest)
    assert state["status"] == "planned"
    assert state["current_stage"] == "H10"
    for row in result["rows"]:
        assert Path(row["reports"]["json"]).is_file()
        assert Path(row["reports"]["markdown"]).is_file()
        assert "/reports/funnel/test/" in row["reports"]["json"]


def test_autopilot_uses_manifest_report_directory(tmp_path: Path, monkeypatch):
    manifest = campaign_manifest(tmp_path)
    payload = json.loads(manifest.read_text())
    payload["stage_output_directories"] = {"reports": "09_reports_and_dialogue"}
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        "masld_agent.funnel.planner.resource_inventory",
        lambda root: {
            "captured_at": "test",
            "cpu_total": 4,
            "cpu_jobs": 3,
            "memory_available_gb": 8,
            "disk_free_gb": 50,
            "gpus": [],
            "available_gpu_ids": [],
        },
    )
    result = run_autopilot(2, manifest_path=manifest, profile="test")
    assert "/09_reports_and_dialogue/funnel/test" in result["report_root"]
    state = autopilot_status(manifest_path=manifest)
    assert "/09_reports_and_dialogue/funnel/AUTOPILOT_STATE.json" in state["state_path"]


def test_preflight_lists_every_missing_enabled_adapter(tmp_path: Path, monkeypatch):
    manifest = campaign_manifest(tmp_path)
    monkeypatch.setattr(
        "masld_agent.funnel.planner.resource_inventory",
        lambda root: {
            "captured_at": "test",
            "cpu_total": 8,
            "cpu_jobs": 6,
            "memory_available_gb": 16,
            "disk_free_gb": 100,
            "gpus": [],
            "available_gpu_ids": [1, 3],
        },
    )
    plan_campaign(2, manifest_path=manifest, profile="test")
    result = preflight_campaign(manifest)
    assert result["status"] == "gated"
    assert result["ready_for_one_shot_execution"] is False
    assert {"H2", "H3", "H4", "H5", "H8"} <= set(result["blocking_stages"])
    assert result["stages"]["H2"]["blockers"] == ["missing_argv_adapter"]
    assert result["stages"]["H6"]["enabled"] is False
    assert result["stages"]["H6"]["ready"] is True


def test_execute_is_gated_before_h1_when_downstream_adapter_is_missing(
    tmp_path: Path,
    monkeypatch,
):
    marker = tmp_path / "h1_started"
    script = tmp_path / "must_not_run.py"
    script.write_text(
        "from pathlib import Path\nPath(%r).write_text('started')\n" % str(marker),
        encoding="utf-8",
    )
    manifest = campaign_manifest(
        tmp_path,
        stages={
            "H1B": {
                "command": [sys.executable, str(script)],
                "outputs": ["dedup/unique.csv"],
            }
        },
    )
    monkeypatch.setattr(
        "masld_agent.funnel.planner.resource_inventory",
        lambda root: {
            "captured_at": "test",
            "cpu_total": 8,
            "cpu_jobs": 6,
            "memory_available_gb": 16,
            "disk_free_gb": 100,
            "gpus": [],
            "available_gpu_ids": [1, 3],
        },
    )
    result = run_autopilot(
        2,
        manifest_path=manifest,
        profile="test",
        execute=True,
        confirm=True,
    )
    assert result["status"] == "gated_preflight"
    assert result["stages_processed"] == 0
    assert "H2" in result["blocking_stages"]
    assert not marker.exists()
    assert Path(result["preflight_report"]).is_file()


def test_background_worker_is_not_spawned_when_preflight_is_gated(
    tmp_path: Path,
    monkeypatch,
):
    manifest = campaign_manifest(tmp_path)
    monkeypatch.setattr(
        "masld_agent.funnel.planner.resource_inventory",
        lambda root: {
            "captured_at": "test",
            "cpu_total": 8,
            "cpu_jobs": 6,
            "memory_available_gb": 16,
            "disk_free_gb": 100,
            "gpus": [],
            "available_gpu_ids": [1, 3],
        },
    )
    result = start_autopilot(
        2,
        manifest_path=manifest,
        profile="test",
        confirm=True,
    )
    assert result["status"] == "gated_preflight"
    assert result["pid"] is None
    assert "H2" in result["blocking_stages"]


def test_stage_runner_requires_confirm_then_validates(tmp_path: Path):
    script = tmp_path / "make_output.py"
    script.write_text(
        "from pathlib import Path\n"
        "p=Path('dedup/unique.csv'); p.parent.mkdir(parents=True, exist_ok=True)\n"
        "p.write_text('molecule_id,smiles\\nM1,CC\\n')\n",
        encoding="utf-8",
    )
    manifest = campaign_manifest(
        tmp_path,
        stages={
            "H1B": {
                "backend": "test_existing_runner",
                "command": [sys.executable, str(script)],
                "outputs": ["dedup/unique.csv"],
            }
        },
    )
    gated = run_stage(manifest, "H1B", execute=True, confirm=False)
    assert gated["status"] == "gated"
    completed = run_stage(manifest, "H1B", execute=True, confirm=True)
    assert completed["status"] == "completed"
    reused = run_stage(manifest, "H1B", execute=True, confirm=True)
    assert reused["reused_existing"] is True


def test_shell_string_is_rejected(tmp_path: Path):
    manifest = campaign_manifest(tmp_path, stages={"H1B": {"command": "echo unsafe"}})
    result = run_stage(manifest, "H1B")
    assert result["status"] == "error"
    assert "argv array" in result["error"]


@pytest.mark.parametrize(
    ("stage", "command", "error"),
    [
        ("H3", ["shape_screen_gpu", "screen", "-osd", "hits.sdf", "-ocsv", "hits.csv"], "-osd"),
        ("H4", ["qikprop", "-inp", "hits.smi"], "structure input"),
        ("H8", ["conda", "run", "desmond"], "must not launch through conda"),
        ("H1B", ["python3", "-c", "print(1)"], "inline shell/Python"),
        ("H2", ["glide", "dock.in", "-WAIT"], "-OVERWRITE"),
    ],
)
def test_known_dialogue_command_failures_are_blocked(
    tmp_path: Path,
    stage: str,
    command: list[str],
    error: str,
):
    manifest = campaign_manifest(tmp_path, stages={stage: {"command": command}})
    result = run_stage(manifest, stage)
    assert result["status"] == "error"
    assert error in result["error"]


def test_compressed_sdf_is_counted_without_text_decode(tmp_path: Path):
    path = tmp_path / "hits.sdfgz"
    with gzip.open(path, "wb") as stream:
        stream.write(b"mol1\n$$$$\nmol2\n$$$$\n")
    result = inspect_sdf(path)
    assert result["status"] == "ok"
    assert result["records"] == 2
    assert result["compressed"] is True


def test_exact_count_validation_rejects_short_csv(tmp_path: Path):
    manifest = campaign_manifest(
        tmp_path,
        stages={
            "H2": {
                "target_count": 2,
                "enforce_exact_count": True,
                "outputs": ["04_glide_sp_top10/top10_parents_manifest.csv"],
            }
        },
    )
    output = manifest.parents[1] / "04_glide_sp_top10/top10_parents_manifest.csv"
    output.parent.mkdir(parents=True)
    output.write_text("molecule_id,score\nM1,-7.0\n", encoding="utf-8")
    result = validate_stage(manifest, "H2")
    assert result["validation"]["valid"] is False
    assert result["validation"]["observed_counts"] == [1]


def test_exact_count_validation_accepts_csv_and_sdf(tmp_path: Path):
    manifest = campaign_manifest(
        tmp_path,
        stages={
            "H3": {
                "target_count": 2,
                "enforce_exact_count": True,
                "outputs": ["hits.csv", "hits.sdf"],
            }
        },
    )
    root = manifest.parents[1]
    (root / "hits.csv").write_text("molecule_id\nM1\nM2\n", encoding="utf-8")
    (root / "hits.sdf").write_bytes(b"mol1\n$$$$\nmol2\n$$$$\n")
    result = validate_stage(manifest, "H3")
    assert result["validation"]["valid"] is True
    assert result["validation"]["observed_counts"] == [2, 2]


def test_prudent_generate_scales_internal_batch_without_writing(tmp_path: Path):
    manifest = campaign_manifest(tmp_path)
    root = manifest.parents[1]
    template = tmp_path / "prudent.yml"
    template.write_text(
        "sample:\n"
        "  seed: 7\n"
        "  dynamic:\n"
        "    prudent:\n"
        "      advance_top_k: 2\n"
        "    large_step:\n"
        "      batch_size: 1\n",
        encoding="utf-8",
    )
    executable = tmp_path / "python"
    sampler = tmp_path / "sample_diffusion.py"
    executable.write_text("python\n", encoding="utf-8")
    sampler.write_text("sample\n", encoding="utf-8")
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    raw["pipeline_targets"] = {"H1B": 100}
    raw["stages"] = {
        "H1B": {
            "config_template": str(template),
            "diffdynamic_python": str(executable),
            "sampler": str(sampler),
        }
    }
    manifest.write_text(json.dumps(raw), encoding="utf-8")
    result = prudent_generate(manifest)
    assert result["status"] == "dry_run"
    assert result["command_preview"]["large_step_batch_size"] == 50
    assert result["command_preview"]["argv"][-1] == "prudent"
    assert not (root / "configs" / "prudent_target_100.yml").exists()


def test_prudent_physchem_disables_vina_and_hands_off_to_glide(tmp_path: Path):
    manifest = campaign_manifest(tmp_path)
    root = manifest.parents[1]
    python = tmp_path / "python"
    evaluator = tmp_path / "evaluate.py"
    pt_path = root / "diffdynamic" / "prudent" / "run" / "result_custom.pt"
    pt_path.parent.mkdir(parents=True)
    for path in (python, evaluator, pt_path):
        path.write_text("present\n", encoding="utf-8")
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    raw["stages"] = {
        "H1B": {
            "pt_path": str(pt_path),
            "diffdynamic_python": str(python),
            "evaluator": str(evaluator),
        }
    }
    manifest.write_text(json.dumps(raw), encoding="utf-8")
    result = prudent_physchem(manifest)
    preview = result["command_preview"]
    argv = preview["argv"]
    assert result["status"] == "dry_run"
    assert argv[argv.index("--vina-modes") + 1] == "none"
    assert preview["vina_executed"] is False
    assert preview["next_stage"].startswith("H2 Glide SP")


def test_stage_runner_executes_configured_steps_in_order(tmp_path: Path):
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.write_text(
        "from pathlib import Path\nPath('first.done').write_text('ok')\n",
        encoding="utf-8",
    )
    second.write_text(
        "from pathlib import Path\n"
        "assert Path('first.done').is_file()\n"
        "p=Path('dedup/unique.csv'); p.parent.mkdir(parents=True, exist_ok=True)\n"
        "p.write_text('molecule_id,smiles\\nM1,CC\\n')\n",
        encoding="utf-8",
    )
    manifest = campaign_manifest(
        tmp_path,
        stages={
            "H1B": {
                "steps": [
                    {"name": "first", "command": [sys.executable, str(first)]},
                    {"name": "second", "command": [sys.executable, str(second)]},
                ]
            }
        },
    )
    result = run_stage(manifest, "H1B", execute=True, confirm=True)
    assert result["status"] == "completed"
    assert len(result["logs"]) == 2


def test_glide_parent_ranking_is_numeric_and_deterministic(tmp_path: Path):
    source = tmp_path / "glide.csv"
    with source.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["parent_id", "r_i_glide_gscore"])
        writer.writeheader()
        writer.writerows(
            [
                {"parent_id": "A", "r_i_glide_gscore": "-7.0"},
                {"parent_id": "A", "r_i_glide_gscore": "-10.0"},
                {"parent_id": "B", "r_i_glide_gscore": "-8.0"},
                {"parent_id": "C", "r_i_glide_gscore": "bad"},
            ]
        )
    output = tmp_path / "top.csv"
    result = rank_glide_parents(source, output, top=2)
    rows = list(csv.DictReader(output.open()))
    assert result["invalid_scores"] == 1
    assert [row["parent_id"] for row in rows] == ["A", "B"]


def test_funnel_tools_register_for_weak_model():
    registered = {}

    class Context:
        def register_tool(self, name=None, schema=None, handler=None, **kwargs):
            registered[name] = {"schema": schema, "handler": handler}

        def register_command(self, *args, **kwargs):
            return None

    register(Context())
    assert "funnel_autopilot" in registered
    schema = registered["funnel_autopilot"]["schema"]
    assert schema["parameters"]["required"] == ["final_count"]
    assert schema["parameters"]["properties"]["profile"]["enum"] == ["full", "test"]
    assert callable(registered["funnel_autopilot"]["handler"])


def test_hermes_turn_limit_is_high_and_syncable(tmp_path: Path):
    config = yaml.safe_load((ROOT / "config/hermes.config.yaml").read_text(encoding="utf-8"))
    assert config["agent"]["max_turns"] >= 600
    launcher = (ROOT / "scripts/start_agent.sh").read_text(encoding="utf-8")
    assert 'HERMES_MAX_TURNS="${HERMES_MAX_TURNS:-600}"' in launcher
    assert '--max-turns "$HERMES_MAX_TURNS"' in launcher

    sync_path = ROOT / "scripts/sync_providers_from_ccswitch.py"
    spec = importlib.util.spec_from_file_location("sync_providers", sync_path)
    assert spec is not None and spec.loader is not None
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)
    output = sync._ensure_config(tmp_path, None, max_turns=600)
    synced = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert synced["agent"]["max_turns"] == 600


def test_funnel_skills_resolve_to_project_and_reject_self_link(tmp_path: Path):
    for name in FUNNEL_FLOWCHART:
        source = _find_skill(name)
        assert source is not None
        assert source.is_relative_to(ROOT / "skills")
    destination = tmp_path / "skill"
    destination.mkdir()
    with pytest.raises(ValueError, match="self-referential"):
        _link_skill(destination, destination, mode="symlink")


def test_frozen_hsd17b13_campaign_is_reused_read_only():
    manifest = Path(
        "/home/user/Desktop/Ye/DiffDynamic/hsvpol/targetmol_t001/"
        "campaign_hsd17b13_pilot100/inputs/manifest.json"
    )
    if not manifest.is_file():
        pytest.skip("frozen HSD17B13 campaign not mounted")
    before = manifest.stat().st_mtime_ns
    status = stage_status(manifest)
    valid = set(status["validated_stages"])
    assert {"H0", "H1B", "H2", "H3", "H4", "H5", "H8"} <= valid
    assert validate_stage(manifest, "H4")["validation"]["valid"] is True
    assert run_stage(manifest, "H8")["reused_existing"] is True
    assert manifest.stat().st_mtime_ns == before
