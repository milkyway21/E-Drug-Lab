from masld_agent.tools.pdb import rank_structures, structure_from_fixture


def test_rank_prefers_experimental_ligand_bound():
    structs = [
        structure_from_fixture(
            {
                "pdb_id": "AF-1",
                "is_alphafold": True,
                "resolution_A": None,
                "organism": "Homo sapiens",
                "bound_ligands": [],
            }
        ),
        structure_from_fixture(
            {
                "pdb_id": "8G9V",
                "is_alphafold": False,
                "resolution_A": 1.9,
                "organism": "Homo sapiens",
                "bound_ligands": ["YXW"],
            }
        ),
    ]
    ranked = rank_structures(structs)
    assert ranked[0].pdb_id == "8G9V"
    assert ranked[0].preferred is True
