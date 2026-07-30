"""湿实验交接服务单测。"""
from unittest.mock import patch

from app.services.wetlab_prep_service import (
    analyze_molecule,
    build_order_pack_xlsx,
    lookup_pubchem,
)


def test_analyze_aspirin_wetlab_ready():
    prep = analyze_molecule(
        "CC(=O)Oc1ccccc1C(=O)O",
        name="aspirin",
        index=1,
        target_code="VAV1",
        batch_id="R1",
        check_pubchem=False,
    )
    assert prep.compound_id.startswith("EDL-VAV1-R1-")
    assert prep.wetlab_ready is True
    assert prep.sa_score is not None
    assert prep.sa_score < 4.0
    assert prep.molecular_weight is not None
    assert prep.dmso_stock_mg_10mm_1ml is not None
    assert prep.dmso_stock_mg_10mm_1ml > 0


def test_invalid_smiles_blocked():
    prep = analyze_molecule("not_a_smiles", check_pubchem=False)
    assert prep.wetlab_ready is False
    assert "无效 SMILES" in prep.blockers[0]


def test_order_pack_xlsx_bytes():
  preps = [
      analyze_molecule("CC(=O)Oc1ccccc1C(=O)O", name="aspirin", index=1, check_pubchem=False),
      analyze_molecule("CCO", name="ethanol", index=2, check_pubchem=False),
  ]
  data = build_order_pack_xlsx(preps, target_name="VAV1", round_id=1)
  assert data[:2] == b"PK"
  assert len(data) > 500


@patch("app.services.wetlab_prep_service.urllib.request.urlopen")
def test_pubchem_lookup_match(mock_urlopen):
    mock_urlopen.return_value.__enter__.return_value.read.return_value = (
        b'{"IdentifierList": {"CID": [2244]}}'
    )
    result = lookup_pubchem("CC(=O)Oc1ccccc1C(=O)O")
    assert result["pubchem_cid"] == 2244
    assert result["sourcing_hint"] == "pubchem_exact_match"
