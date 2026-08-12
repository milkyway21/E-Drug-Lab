"""Hard gates for platform compute."""
from __future__ import annotations

import pytest

from masld_agent.platform.gates import (
    GateError,
    gate_diffdynamic_generate,
    gate_schrodinger_dock,
    require_confirm,
)


def test_require_confirm_blocks():
    with pytest.raises(GateError):
        require_confirm(False, reason="test")
    require_confirm(True, reason="test")


def test_dd_requires_protein_ligand(tmp_path):
    with pytest.raises(GateError):
        gate_diffdynamic_generate(
            mode="denovo_fast",
            protein_path=None,
            ligand_path=None,
            molecule_path=None,
            batch_size=10,
            confirm=False,
        )


def test_dd_scaffold_requires_molecule(tmp_path):
    prot = tmp_path / "p.pdb"
    lig = tmp_path / "l.sdf"
    prot.write_text("ATOM\n")
    lig.write_text("mol\n")
    with pytest.raises(GateError, match="scaffold"):
        gate_diffdynamic_generate(
            mode="scaffold_fast",
            protein_path=str(prot),
            ligand_path=str(lig),
            molecule_path=None,
            batch_size=10,
            confirm=False,
        )


@pytest.mark.parametrize(
    ("protein_name", "ligand_name", "message"),
    [
        ("p.cif", "l.sdf", r"protein must be a \.pdb"),
        ("p.pdb", "l.mol2", r"ligand must be a \.sdf"),
    ],
)
def test_dd_rejects_noncanonical_input_formats(
    tmp_path,
    protein_name,
    ligand_name,
    message,
):
    protein = tmp_path / protein_name
    ligand = tmp_path / ligand_name
    protein.write_text("ATOM\n")
    ligand.write_text("mol\n")
    with pytest.raises(GateError, match=message):
        gate_diffdynamic_generate(
            mode="denovo_fast",
            protein_path=str(protein),
            ligand_path=str(ligand),
            molecule_path=None,
            batch_size=10,
            confirm=False,
        )


def test_dd_scaffold_rejects_non_sdf_molecule(tmp_path):
    protein = tmp_path / "p.pdb"
    ligand = tmp_path / "l.sdf"
    molecule = tmp_path / "scaffold.mol2"
    for path in (protein, ligand, molecule):
        path.write_text("nonempty\n")
    with pytest.raises(GateError, match=r"scaffold must be a \.sdf"):
        gate_diffdynamic_generate(
            mode="scaffold_fast",
            protein_path=str(protein),
            ligand_path=str(ligand),
            molecule_path=str(molecule),
            batch_size=10,
            confirm=False,
        )


def test_dd_large_batch_needs_confirm(tmp_path):
    prot = tmp_path / "p.pdb"
    lig = tmp_path / "l.sdf"
    prot.write_text("ATOM\n")
    lig.write_text("mol\n")
    with pytest.raises(GateError, match="confirm"):
        gate_diffdynamic_generate(
            mode="denovo_fast",
            protein_path=str(prot),
            ligand_path=str(lig),
            molecule_path=None,
            batch_size=100,
            confirm=False,
        )
    g = gate_diffdynamic_generate(
        mode="denovo_fast",
        protein_path=str(prot),
        ligand_path=str(lig),
        molecule_path=None,
        batch_size=100,
        confirm=True,
    )
    assert "dd.mode.denovo_fast" in g["catalog_ids"]


def test_sz_xp_needs_confirm(tmp_path):
    rec = tmp_path / "r.pdb"
    rec.write_text("ATOM\n")
    with pytest.raises(GateError, match="confirm"):
        gate_schrodinger_dock(
            receptor_pdb=str(rec),
            n_ligands=2,
            confirm=False,
            precision="XP",
        )
    g = gate_schrodinger_dock(
        receptor_pdb=str(rec),
        n_ligands=2,
        confirm=True,
        precision="SP",
    )
    assert "sz.glide_sp" in g["catalog_ids"]
