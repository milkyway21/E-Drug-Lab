"""Tests for tool registry and pipeline orchestration."""
from __future__ import annotations

import pytest

from app.core.tool_registry import TOOL_REGISTRY, get_tool, list_steps, list_tools
from app.core.workflow_steps import STEP_ID_ADMET, STEP_ORDER
from app.services.pipeline_eval_bridge import build_evaluated_dataframe, DEFAULT_COLUMN_MAPPING
from app.services.job_store import JobStore


def test_tool_registry_contains_core_tools():
    assert "drugclip" in TOOL_REGISTRY
    assert "diffdynamic" in TOOL_REGISTRY
    assert "vina-dock" in TOOL_REGISTRY
    assert "orthogonal-rank" in TOOL_REGISTRY
    tool = get_tool("drugclip")
    assert tool.step_id == "virtual_screen"
    assert tool.output_key == "drugclip"


def test_list_tools_and_steps():
    tools = list_tools()
    steps = list_steps()
    assert len(tools) >= 15
    assert len(steps) == 8
    assert any(s["id"] == STEP_ID_ADMET for s in steps)


def test_step_order():
    assert STEP_ORDER[0] == "target_prep"
    assert "ranking" in STEP_ORDER


def test_build_evaluated_dataframe_with_mapping():
    molecules = [
        {
            "id": "mol-1",
            "smiles": "CCO",
            "name": "ethanol",
            "properties": {"qed": 0.5, "molecular_weight": 46},
            "stepResults": {
                "vina-dock": {"affinity_kcal_mol": -7.5},
                "orthogonal-rank": {"final_score": 82.0},
            },
        }
    ]
    df = build_evaluated_dataframe(molecules, round_id=1)
    assert len(df) == 1
    assert df.iloc[0]["vina_score"] == -7.5
    assert df.iloc[0]["oracle_score_prelim"] == 82.0


def test_build_evaluated_dataframe_custom_mapping():
    molecules = [{"id": "m1", "smiles": "C", "custom_score": 99}]
    mapping = {"custom_score": "custom_score"}
    df = build_evaluated_dataframe(
        molecules,
        round_id=1,
        column_mapping=mapping,
        extra_columns=["custom_score"],
    )
    assert "custom_score" in df.columns


def test_job_store_list_by_run_id():
    store = JobStore()
    run_id = "run-abc"
    j1 = store.create("test", pipeline_run_id=run_id)
    store.create("other", pipeline_run_id="other-run")
    jobs = store.list_by_run_id(run_id)
    assert len(jobs) == 1
    assert jobs[0]["id"] == j1
    assert jobs[0]["pipeline_run_id"] == run_id


def test_merge_all_must_pass_logic():
    def merge_all_must_pass(molecule_ids, passed_per_tool):
        if not passed_per_tool:
            return molecule_ids, []
        sets = [set(ids) for ids in passed_per_tool]
        passed = [mid for mid in molecule_ids if all(mid in s for s in sets)]
        failed = [mid for mid in molecule_ids if mid not in passed]
        return passed, failed

    ids = ["a", "b", "c"]
    passed, failed = merge_all_must_pass(ids, [["a", "b"], ["a", "c"]])
    assert passed == ["a"]
    assert failed == ["b", "c"]
