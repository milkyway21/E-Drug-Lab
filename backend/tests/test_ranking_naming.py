from datetime import datetime

from app.api.routes.ranking import _build_report_rows, _build_standard_name
from app.api.routes.ranking import MoleculePersistenceRecord
from app.services.orthogonal_scoring import OrthogonalRankResult


def test_build_standard_name_uses_expected_format():
    stamp = datetime(2026, 6, 11, 1, 41)
    assert _build_standard_name("8V1T", 80.46, "TAME-VS", stamp) == "8v1t_80p46_tamevs_202606110141"


def test_build_report_rows_preserves_original_name_and_sets_standard_name():
    ranked = [
        OrthogonalRankResult(
            molecule_id="mol-1",
            name="aspirin",
            primary_value=-7.8,
            orthogonal_value=0.81,
            primary_desirability=75.0,
            orthogonal_desirability=75.0,
            consistency_gap=0.0,
            final_score=80.46,
            artifact_flag=False,
            artifact_reason=None,
            selected_primary_model="vina",
            selected_orthogonal_model="admet-ai",
        )
    ]
    records = {
        "mol-1": MoleculePersistenceRecord(
            molecule_id="mol-1",
            name="aspirin",
            smiles="CC(=O)OC1=CC=CC=C1C(=O)O",
            source="TAME-VS",
            source_db_id="db-1",
            status="pass",
        )
    }

    rows = _build_report_rows(ranked, records, "8v1t", datetime(2026, 6, 11, 1, 41))

    assert rows[0]["original_name"] == "aspirin"
    assert rows[0]["standard_name"] == "8v1t_80p46_tamevs_202606110141"
