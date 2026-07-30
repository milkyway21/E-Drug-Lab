from masld_agent.tools.pubchem import parse_pubchem_properties


def test_parse_pubchem_properties():
    raw = {
        "PropertyTable": {
            "Properties": [
                {
                    "CID": 2244,
                    "CanonicalSMILES": "CC(=O)OC1=CC=CC=C1C(=O)O",
                    "InChIKey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
                    "IUPACName": "aspirin",
                    "MolecularWeight": 180.16,
                }
            ]
        }
    }
    parsed = parse_pubchem_properties(raw)
    assert parsed["cid"] == 2244
    assert parsed["smiles"].startswith("CC(=O)OC1")
