from masld_agent.tools.rdkit_eval import evaluate_smiles
from masld_agent.tools.docking import run_docking


def test_rdkit_ethanol():
    r = evaluate_smiles("CCO")
    if r.get("status") == "skipped_missing_dependency":
        return
    assert r["status"] == "ok"
    assert r["MW"] > 0


def test_docking_skip_without_vina():
    d = run_docking()
    assert d.status in {
        "skipped_missing_dependency",
        "failed",
        "skipped_incomplete_integration",
    }
    assert d.score is None
    assert d.label == "computational_prediction"
