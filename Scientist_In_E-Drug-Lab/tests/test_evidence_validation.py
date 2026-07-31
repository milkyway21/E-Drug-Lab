from masld_agent.tools.pubchem import parse_pubchem_properties
from masld_agent.tools.uniprot import resolve_human_gene


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


def test_resolve_uniprot_prefers_ensembl_gene_id(monkeypatch):
    record = {
        "primaryAccession": "Q7Z5P4",
        "genes": [{"geneName": {"value": "HSD17B13"}}],
        "uniProtKBCrossReferences": [
            {
                "database": "Ensembl",
                "id": "ENST00000302219.8",
                "properties": [
                    {"key": "GeneId", "value": "ENSG00000149084.13"},
                ],
            }
        ],
    }
    monkeypatch.setattr(
        "masld_agent.tools.uniprot.search_human_gene",
        lambda gene, **kwargs: [record],
    )

    resolved = resolve_human_gene("HSD17B13")

    assert resolved["ensembl_id"] == "ENSG00000149084"
