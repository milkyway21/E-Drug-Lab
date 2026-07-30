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
