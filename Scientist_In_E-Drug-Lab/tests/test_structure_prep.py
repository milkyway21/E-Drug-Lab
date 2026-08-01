from __future__ import annotations

import csv
from pathlib import Path

import pytest
from rdkit import Chem

from masld_agent.tools.structure_prep import parse_mmcif_atoms, prepare_native_structure


def _pdb_atom(
    record: str,
    serial: int,
    atom_name: str,
    resname: str,
    chain: str,
    resseq: int,
    x: float,
    y: float,
    z: float,
    element: str,
    *,
    occupancy: float = 1.0,
    altloc: str = "",
) -> str:
    return (
        f"{record:<6}{serial:>5} {atom_name:^4}{altloc:1}{resname:>3} {chain:1}"
        f"{resseq:>4}    {x:>8.3f}{y:>8.3f}{z:>8.3f}{occupancy:>6.2f}{20.0:>6.2f}"
        f"          {element:>2}"
    )


def _write_fixture(path: Path) -> None:
    lines = [
        _pdb_atom("ATOM", 1, "N", "ALA", "A", 1, 0.0, 0.0, 0.0, "N"),
        _pdb_atom("ATOM", 2, "CA", "ALA", "A", 1, 1.5, 0.0, 0.0, "C"),
        _pdb_atom("ATOM", 3, "C", "ALA", "A", 1, 2.5, 1.0, 0.0, "C"),
        _pdb_atom("ATOM", 4, "N", "ALA", "B", 1, 50.0, 50.0, 50.0, "N"),
        _pdb_atom("HETATM", 10, "O", "HOH", "A", 100, 3.0, 3.0, 3.0, "O"),
        _pdb_atom("HETATM", 20, "C1", "LIG", "A", 500, 1.0, 1.0, 1.0, "C"),
        _pdb_atom("HETATM", 21, "O1", "LIG", "A", 500, 2.2, 1.0, 1.0, "O"),
        _pdb_atom("HETATM", 22, "N1", "LIG", "A", 500, 0.0, 1.0, 1.0, "N"),
        _pdb_atom("HETATM", 30, "C1", "LIG", "B", 600, 60.0, 60.0, 60.0, "C"),
        _pdb_atom("HETATM", 31, "O1", "LIG", "B", 600, 61.2, 60.0, 60.0, "O"),
        _pdb_atom("HETATM", 32, "N1", "LIG", "B", 600, 59.0, 60.0, 60.0, "N"),
        "CONECT   20   21   22",
        "CONECT   21   20",
        "CONECT   22   20",
        "END",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_ccd(path: Path, component_id: str = "LIG") -> None:
    path.write_text(
        f"""data_{component_id}
#
loop_
_chem_comp_atom.comp_id
_chem_comp_atom.atom_id
_chem_comp_atom.type_symbol
_chem_comp_atom.charge
{component_id} C1 C 0
{component_id} O1 O 0
{component_id} N1 N 0
#
loop_
_chem_comp_bond.comp_id
_chem_comp_bond.atom_id_1
_chem_comp_bond.atom_id_2
_chem_comp_bond.value_order
{component_id} C1 O1 DOUB
{component_id} C1 N1 SING
#
""",
        encoding="utf-8",
    )


def _write_mmcif_fixture(path: Path) -> None:
    path.write_text(
        """data_1ABC
#
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_alt_id
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_entity_id
_atom_site.label_seq_id
_atom_site.pdbx_PDB_ins_code
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.occupancy
_atom_site.B_iso_or_equiv
_atom_site.auth_seq_id
_atom_site.auth_comp_id
_atom_site.auth_asym_id
_atom_site.auth_atom_id
_atom_site.pdbx_PDB_model_num
ATOM 1 N N . ALA A 1 1 ? 0.000 0.000 0.000 1.00 20.0 1 ALA A N 1
ATOM 2 C CA . ALA A 1 1 ? 1.500 0.000 0.000 1.00 20.0 1 ALA A CA 1
ATOM 3 C C . ALA A 1 1 ? 2.500 1.000 0.000 1.00 20.0 1 ALA A C 1
HETATM 10 O O . HOH W 2 . ? 3.000 3.000 3.000 1.00 20.0 100 HOH A O 1
HETATM 20 C C1 . A1AG4 L 3 . ? 1.000 1.000 1.000 1.00 20.0 500 A1AG4 A C1 1
HETATM 21 O O1 . A1AG4 L 3 . ? 2.200 1.000 1.000 1.00 20.0 500 A1AG4 A O1 1
HETATM 22 N N1 . A1AG4 L 3 . ? 0.000 1.000 1.000 1.00 20.0 500 A1AG4 A N1 1
#
""",
        encoding="utf-8",
    )


def test_prepare_native_structure_keeps_ligand_in_receptor_frame(tmp_path: Path) -> None:
    source = tmp_path / "source.pdb"
    ccd = tmp_path / "LIG.cif"
    output = tmp_path / "prepared"
    _write_fixture(source)
    _write_ccd(ccd)

    manifest = prepare_native_structure(
        pdb_id="1abc",
        ligand_id="LIG",
        output_dir=output,
        chains=["A"],
        source_pdb=source,
        ccd_cif=ccd,
    )

    selected = manifest["selected_ligand_instance"]
    assert selected["chain"] == "A"
    assert selected["resseq"] == 500
    assert selected["contact_atom_count_5A"] == 3
    assert manifest["coordinate_validation"]["same_coordinate_frame"] is True
    assert manifest["coordinate_validation"]["translation_or_rotation_applied"] is False
    assert manifest["coordinate_validation"]["sdf_max_abs_coordinate_delta_A"] == 0.0
    assert manifest["pocket_center"]["center_xyz_A"] == [1.0667, 1.0, 1.0]

    receptor = (output / "receptor/1ABC_receptor_clean.pdb").read_text(encoding="utf-8")
    assert " A   1" in receptor
    assert " B   1" not in receptor
    assert "LIG" not in receptor
    assert "HOH" not in receptor

    ligand_pdb = next((output / "ligand").glob("*_native.pdb"))
    ligand_text = ligand_pdb.read_text(encoding="utf-8")
    assert "LIG A 500" in ligand_text
    assert "  60.000  60.000  60.000" not in ligand_text

    ligand_sdf = next((output / "ligand").glob("*_native.sdf"))
    molecule = Chem.SDMolSupplier(str(ligand_sdf), removeHs=False, sanitize=False)[0]
    assert molecule is not None
    assert molecule.GetNumAtoms() == 3
    assert molecule.GetNumBonds() == 2
    point = molecule.GetConformer().GetAtomPosition(0)
    assert (round(point.x, 3), round(point.y, 3), round(point.z, 3)) == (1.0, 1.0, 1.0)

    with (output / "ligand_instances.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2
    assert sum(row["selected"] == "True" for row in rows) == 1


def test_prepare_native_structure_honors_explicit_ligand_copy(tmp_path: Path) -> None:
    source = tmp_path / "source.pdb"
    ccd = tmp_path / "LIG.cif"
    _write_fixture(source)
    _write_ccd(ccd)

    manifest = prepare_native_structure(
        pdb_id="1abc",
        ligand_id="LIG",
        output_dir=tmp_path / "explicit",
        chains=["A"],
        ligand_chain="B",
        ligand_resseq=600,
        source_pdb=source,
        ccd_cif=ccd,
    )

    selected = manifest["selected_ligand_instance"]
    assert selected["chain"] == "B"
    assert selected["resseq"] == 600
    assert selected["selection_reason"] == "explicit_or_unique_instance"


def test_prepare_native_structure_supports_mmcif_and_long_ccd_ids(tmp_path: Path) -> None:
    source = tmp_path / "source.cif"
    ccd = tmp_path / "A1AG4.cif"
    output = tmp_path / "mmcif"
    _write_mmcif_fixture(source)
    _write_ccd(ccd, "A1AG4")

    manifest = prepare_native_structure(
        pdb_id="1abc",
        ligand_id="A1AG4",
        output_dir=output,
        chains=["A"],
        source_mmcif=source,
        ccd_cif=ccd,
    )

    assert manifest["source_coordinate_format"] == "mmcif"
    assert manifest["selected_ligand_instance"]["chain"] == "A"
    assert manifest["coordinate_validation"]["sdf_max_abs_coordinate_delta_A"] == 0.0
    assert (output / "receptor/1ABC_receptor_clean.pdb").is_file()
    ligand_cif = next((output / "ligand").glob("*_native.cif"))
    ligand_atoms = parse_mmcif_atoms(ligand_cif.read_text(encoding="utf-8"))
    assert len(ligand_atoms) == 3
    assert (ligand_atoms[0].x, ligand_atoms[0].y, ligand_atoms[0].z) == (1.0, 1.0, 1.0)
    assert not list((output / "ligand").glob("*_native.pdb"))
    assert "legacy_pdb_ligand_not_written:mmcif_and_sdf_required" in manifest["warnings"]


def test_prepare_native_structure_blocks_explicit_covalent_ligand(tmp_path: Path) -> None:
    source = tmp_path / "covalent.pdb"
    ccd = tmp_path / "LIG.cif"
    _write_fixture(source)
    source.write_text(
        source.read_text(encoding="utf-8").replace("END\n", "CONECT   20    2\nEND\n"),
        encoding="utf-8",
    )
    _write_ccd(ccd)

    with pytest.raises(ValueError, match="explicit covalent link"):
        prepare_native_structure(
            pdb_id="1abc",
            ligand_id="LIG",
            output_dir=tmp_path / "blocked",
            chains=["A"],
            source_pdb=source,
            ccd_cif=ccd,
        )
