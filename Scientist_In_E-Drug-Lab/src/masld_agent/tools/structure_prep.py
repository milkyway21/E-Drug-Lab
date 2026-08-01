"""Download and prepare a native protein-ligand coordinate set from RCSB PDB."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
from rdkit import Chem
from rdkit.Geometry import Point3D

from masld_agent.http_cache import CachedHttp


RCSB_COORDINATE_URL = "https://files.rcsb.org/download/{pdb_id}.pdb"
RCSB_CIF_URL = "https://files.rcsb.org/download/{pdb_id}.cif"
RCSB_CCD_URL = "https://files.rcsb.org/ligands/download/{ligand_id}.cif"
WATER_COMPONENTS = {"HOH", "WAT", "H2O", "DOD"}
PROTEIN_LIKE_HETERO = {"MSE", "SEC", "PYL", "SEP", "TPO", "PTR", "HYP", "CSO"}
PDB_ID_PATTERN = re.compile(r"^[A-Z0-9]{4}$")
CCD_ID_PATTERN = re.compile(r"^[A-Z0-9]{1,16}$")


@dataclass(frozen=True)
class PdbAtom:
    line_index: int
    line: str
    record_type: str
    serial: int
    atom_name: str
    altloc: str
    resname: str
    chain: str
    resseq: int
    icode: str
    x: float
    y: float
    z: float
    occupancy: float
    element: str

    @property
    def residue_key(self) -> tuple[str, str, int, str]:
        return (self.resname, self.chain, self.resseq, self.icode)

    @property
    def atom_key(self) -> tuple[str, str, int, str, str, str]:
        return (
            self.record_type,
            self.chain,
            self.resseq,
            self.icode,
            self.resname,
            self.atom_name,
        )

    @property
    def is_heavy(self) -> bool:
        return self.element.upper() not in {"H", "D"}


@dataclass(frozen=True)
class LigandInstance:
    atoms: tuple[PdbAtom, ...]
    contact_atom_count: int
    min_distance_A: float

    @property
    def key(self) -> tuple[str, str, int, str]:
        return self.atoms[0].residue_key

    @property
    def heavy_atom_count(self) -> int:
        return sum(atom.is_heavy for atom in self.atoms)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def _safe_file_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value) or "blank"


def _element_from_atom_name(atom_name: str) -> str:
    letters = "".join(character for character in atom_name if character.isalpha())
    return (letters[:1] or "C").upper()


def _parse_atom_line(line: str, line_index: int) -> PdbAtom:
    if len(line) < 54:
        raise ValueError(f"invalid PDB coordinate line {line_index + 1}: fewer than 54 columns")
    record_type = line[:6].strip().upper()
    if record_type not in {"ATOM", "HETATM"}:
        raise ValueError(f"not a coordinate record: {record_type}")
    try:
        serial = int(line[6:11].strip())
        resseq = int(line[22:26].strip())
        x = float(line[30:38].strip())
        y = float(line[38:46].strip())
        z = float(line[46:54].strip())
        occupancy = float(line[54:60].strip() or 0.0)
    except ValueError as exc:
        raise ValueError(f"invalid PDB coordinate fields on line {line_index + 1}") from exc
    return PdbAtom(
        line_index=line_index,
        line=line.rstrip("\n"),
        record_type=record_type,
        serial=serial,
        atom_name=line[12:16].strip(),
        altloc=line[16:17].strip(),
        resname=line[17:20].strip().upper(),
        chain=line[21:22].strip(),
        resseq=resseq,
        icode=line[26:27].strip(),
        x=x,
        y=y,
        z=z,
        occupancy=occupancy,
        element=(line[76:78].strip() or _element_from_atom_name(line[12:16])).upper(),
    )


def _pdb_compatible(atom: PdbAtom) -> bool:
    return (
        0 < atom.serial <= 99999
        and len(atom.atom_name) <= 4
        and len(atom.resname) <= 3
        and len(atom.chain) <= 1
        and -999 <= atom.resseq <= 9999
        and -999.999 <= atom.x <= 9999.999
        and -999.999 <= atom.y <= 9999.999
        and -999.999 <= atom.z <= 9999.999
    )


def _format_pdb_atom(atom: PdbAtom) -> str:
    if not _pdb_compatible(atom):
        raise ValueError(
            f"atom cannot be represented without loss in legacy PDB format: {atom.residue_key}"
        )
    return (
        f"{atom.record_type:<6}{atom.serial:>5} {atom.atom_name:^4}{atom.altloc:1}"
        f"{atom.resname:>3} {atom.chain:1}{atom.resseq:>4}{atom.icode:1}   "
        f"{atom.x:>8.3f}{atom.y:>8.3f}{atom.z:>8.3f}{atom.occupancy:>6.2f}"
        f"{0.0:>6.2f}          {atom.element:>2}"
    )


def parse_pdb_atoms(text: str, *, model: int = 1) -> list[PdbAtom]:
    atoms: list[PdbAtom] = []
    current_model = 1
    saw_model = False
    for line_index, line in enumerate(text.splitlines()):
        record_type = line[:6].strip().upper()
        if record_type == "MODEL":
            saw_model = True
            try:
                current_model = int(line[10:14].strip())
            except ValueError:
                current_model += 1
            continue
        if record_type == "ENDMDL":
            continue
        if record_type not in {"ATOM", "HETATM"}:
            continue
        if saw_model and current_model != model:
            continue
        atoms.append(_parse_atom_line(line, line_index))
    if not atoms:
        raise ValueError(f"no ATOM/HETATM records found for model {model}")
    return atoms


def _clean_cif_value(value: str) -> str:
    return "" if value in {"", ".", "?"} else value


def _cif_row_value(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = _clean_cif_value(row.get(key, ""))
        if value:
            return value
    return ""


def parse_mmcif_atoms(text: str, *, model: int = 1) -> list[PdbAtom]:
    """Parse an atom_site loop using author chain and residue numbering."""
    rows = _ccd_table(text, "_atom_site.")
    atoms: list[PdbAtom] = []
    for line_index, row in enumerate(rows):
        row_model = int(float(_cif_row_value(row, "_atom_site.pdbx_PDB_model_num") or "1"))
        if row_model != model:
            continue
        record_type = _cif_row_value(row, "_atom_site.group_PDB").upper()
        if record_type not in {"ATOM", "HETATM"}:
            continue
        try:
            atom = PdbAtom(
                line_index=line_index,
                line="",
                record_type=record_type,
                serial=int(float(_cif_row_value(row, "_atom_site.id"))),
                atom_name=_cif_row_value(
                    row, "_atom_site.label_atom_id", "_atom_site.auth_atom_id"
                ),
                altloc=_cif_row_value(row, "_atom_site.label_alt_id"),
                resname=_cif_row_value(
                    row, "_atom_site.label_comp_id", "_atom_site.auth_comp_id"
                ).upper(),
                chain=_cif_row_value(row, "_atom_site.auth_asym_id", "_atom_site.label_asym_id"),
                resseq=int(
                    float(_cif_row_value(row, "_atom_site.auth_seq_id", "_atom_site.label_seq_id"))
                ),
                icode=_cif_row_value(row, "_atom_site.pdbx_PDB_ins_code"),
                x=float(_cif_row_value(row, "_atom_site.Cartn_x")),
                y=float(_cif_row_value(row, "_atom_site.Cartn_y")),
                z=float(_cif_row_value(row, "_atom_site.Cartn_z")),
                occupancy=float(_cif_row_value(row, "_atom_site.occupancy") or "0"),
                element=_cif_row_value(row, "_atom_site.type_symbol").upper(),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid mmCIF atom_site row {line_index + 1}") from exc
        atoms.append(atom)
    if not atoms:
        raise ValueError(f"no ATOM/HETATM rows found for mmCIF model {model}")
    return atoms


def _select_altlocs(atoms: Iterable[PdbAtom]) -> list[PdbAtom]:
    selected: dict[tuple[str, str, int, str, str, str], PdbAtom] = {}
    for atom in atoms:
        current = selected.get(atom.atom_key)
        if current is None:
            selected[atom.atom_key] = atom
            continue
        atom_priority = (atom.occupancy, atom.altloc == "", atom.altloc == "A")
        current_priority = (current.occupancy, current.altloc == "", current.altloc == "A")
        if atom_priority > current_priority:
            selected[atom.atom_key] = atom
    return sorted(selected.values(), key=lambda atom: atom.line_index)


def _ligand_instances(
    atoms: list[PdbAtom],
    receptor_atoms: list[PdbAtom],
    ligand_id: str,
) -> list[LigandInstance]:
    grouped: dict[tuple[str, str, int, str], list[PdbAtom]] = {}
    for atom in atoms:
        if atom.record_type == "HETATM" and atom.resname == ligand_id:
            grouped.setdefault(atom.residue_key, []).append(atom)
    receptor_heavy = [atom for atom in receptor_atoms if atom.is_heavy]
    receptor_coordinates = np.asarray(
        [(atom.x, atom.y, atom.z) for atom in receptor_heavy], dtype=float
    )
    instances: list[LigandInstance] = []
    for ligand_atoms in grouped.values():
        heavy = [atom for atom in ligand_atoms if atom.is_heavy]
        ligand_coordinates = np.asarray([(atom.x, atom.y, atom.z) for atom in heavy], dtype=float)
        if ligand_coordinates.size and receptor_coordinates.size:
            delta = ligand_coordinates[:, np.newaxis, :] - receptor_coordinates[np.newaxis, :, :]
            squared_distances = np.einsum("ijk,ijk->ij", delta, delta)
            per_atom_minimum = np.min(squared_distances, axis=1)
            contacting = int(np.count_nonzero(per_atom_minimum <= 25.0))
            min_distance = float(math.sqrt(float(np.min(per_atom_minimum))))
        else:
            contacting = 0
            min_distance = float("inf")
        instances.append(
            LigandInstance(
                atoms=tuple(sorted(ligand_atoms, key=lambda atom: atom.line_index)),
                contact_atom_count=contacting,
                min_distance_A=min_distance,
            )
        )
    return instances


def _select_ligand_instance(
    instances: list[LigandInstance],
    *,
    ligand_chain: Optional[str],
    ligand_resseq: Optional[int],
    ligand_icode: Optional[str],
) -> tuple[LigandInstance, str]:
    candidates = instances
    if ligand_chain is not None:
        candidates = [item for item in candidates if item.key[1] == ligand_chain]
    if ligand_resseq is not None:
        candidates = [item for item in candidates if item.key[2] == ligand_resseq]
    if ligand_icode is not None:
        candidates = [item for item in candidates if item.key[3] == ligand_icode]
    if not candidates:
        raise ValueError("requested ligand instance was not found in the selected coordinate model")
    if len(candidates) == 1:
        return candidates[0], "explicit_or_unique_instance"
    ranked = sorted(
        candidates,
        key=lambda item: (
            -item.contact_atom_count,
            item.min_distance_A,
            -item.heavy_atom_count,
            item.key[1],
            item.key[2],
            item.key[3],
        ),
    )
    return ranked[0], "highest_target_chain_contact_then_distance_then_heavy_atom_count"


def _pdb_text(
    atoms: list[PdbAtom], *, remarks: list[str], conect_lines: list[str] | None = None
) -> str:
    lines = [f"REMARK 950 {remark}"[:80] for remark in remarks]
    previous_chain: Optional[str] = None
    for atom in atoms:
        if previous_chain is not None and atom.chain != previous_chain:
            lines.append("TER")
        lines.append(atom.line or _format_pdb_atom(atom))
        previous_chain = atom.chain
    if atoms:
        lines.append("TER")
    lines.extend(conect_lines or [])
    lines.append("END")
    return "\n".join(lines) + "\n"


def _cif_token(value: Any) -> str:
    text = str(value)
    if not text:
        return "?"
    if any(character.isspace() for character in text) or text.startswith(("_", "#", ";")):
        return "'" + text.replace("'", "''") + "'"
    return text


def _mmcif_text(atoms: list[PdbAtom], *, data_name: str, remarks: list[str]) -> str:
    lines = [f"data_{re.sub(r'[^A-Za-z0-9_]', '_', data_name)}", "#"]
    lines.extend(f"# E-Drug-Lab: {remark}" for remark in remarks)
    lines.extend(
        [
            "#",
            "loop_",
            "_atom_site.group_PDB",
            "_atom_site.id",
            "_atom_site.type_symbol",
            "_atom_site.label_atom_id",
            "_atom_site.label_alt_id",
            "_atom_site.label_comp_id",
            "_atom_site.label_asym_id",
            "_atom_site.label_entity_id",
            "_atom_site.label_seq_id",
            "_atom_site.pdbx_PDB_ins_code",
            "_atom_site.Cartn_x",
            "_atom_site.Cartn_y",
            "_atom_site.Cartn_z",
            "_atom_site.occupancy",
            "_atom_site.B_iso_or_equiv",
            "_atom_site.auth_seq_id",
            "_atom_site.auth_comp_id",
            "_atom_site.auth_asym_id",
            "_atom_site.auth_atom_id",
            "_atom_site.pdbx_PDB_model_num",
        ]
    )
    for atom in atoms:
        values = [
            atom.record_type,
            atom.serial,
            atom.element,
            atom.atom_name,
            atom.altloc or ".",
            atom.resname,
            atom.chain or ".",
            "?",
            atom.resseq if atom.record_type == "ATOM" else ".",
            atom.icode or "?",
            f"{atom.x:.3f}",
            f"{atom.y:.3f}",
            f"{atom.z:.3f}",
            f"{atom.occupancy:.2f}",
            "0.00",
            atom.resseq,
            atom.resname,
            atom.chain or ".",
            atom.atom_name,
            1,
        ]
        lines.append(" ".join(_cif_token(value) for value in values))
    lines.extend(["#", ""])
    return "\n".join(lines)


def _filtered_conect_lines(source_text: str, serials: set[int]) -> list[str]:
    output: list[str] = []
    for line in source_text.splitlines():
        if not line.startswith("CONECT"):
            continue
        values = []
        for start in range(6, len(line), 5):
            value = line[start : start + 5].strip()
            if value:
                try:
                    values.append(int(value))
                except ValueError:
                    pass
        if values and values[0] in serials:
            retained = [value for value in values if value in serials]
            if len(retained) > 1:
                output.append("CONECT" + "".join(f"{value:5d}" for value in retained))
    return output


def _conect_pairs(source_text: str) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    for line in source_text.splitlines():
        if not line.startswith("CONECT"):
            continue
        values: list[int] = []
        for start in range(6, len(line), 5):
            try:
                values.append(int(line[start : start + 5].strip()))
            except ValueError:
                continue
        if values:
            pairs.update(tuple(sorted((values[0], target))) for target in values[1:])
    return pairs


def _pdb_link_residue_pairs(source_text: str) -> set[tuple[tuple[str, str, int, str], ...]]:
    pairs: set[tuple[tuple[str, str, int, str], ...]] = set()
    for line in source_text.splitlines():
        if not line.startswith("LINK"):
            continue
        try:
            first = (
                line[17:20].strip().upper(),
                line[21:22].strip(),
                int(line[22:26].strip()),
                line[26:27].strip(),
            )
            second = (
                line[47:50].strip().upper(),
                line[51:52].strip(),
                int(line[52:56].strip()),
                line[56:57].strip(),
            )
        except ValueError:
            continue
        pairs.add((first, second))
    return pairs


def _mmcif_covalent_residue_pairs(
    source_text: str,
) -> set[tuple[tuple[str, str, int, str], ...]]:
    try:
        rows = _ccd_table(source_text, "_struct_conn.")
    except ValueError:
        return set()
    pairs: set[tuple[tuple[str, str, int, str], ...]] = set()
    for row in rows:
        if not _cif_row_value(row, "_struct_conn.conn_type_id").lower().startswith("covale"):
            continue
        try:
            first = (
                _cif_row_value(
                    row,
                    "_struct_conn.ptnr1_label_comp_id",
                    "_struct_conn.ptnr1_auth_comp_id",
                ).upper(),
                _cif_row_value(
                    row,
                    "_struct_conn.ptnr1_auth_asym_id",
                    "_struct_conn.ptnr1_label_asym_id",
                ),
                int(
                    float(
                        _cif_row_value(
                            row,
                            "_struct_conn.ptnr1_auth_seq_id",
                            "_struct_conn.ptnr1_label_seq_id",
                        )
                    )
                ),
                _cif_row_value(row, "_struct_conn.pdbx_ptnr1_PDB_ins_code"),
            )
            second = (
                _cif_row_value(
                    row,
                    "_struct_conn.ptnr2_label_comp_id",
                    "_struct_conn.ptnr2_auth_comp_id",
                ).upper(),
                _cif_row_value(
                    row,
                    "_struct_conn.ptnr2_auth_asym_id",
                    "_struct_conn.ptnr2_label_asym_id",
                ),
                int(
                    float(
                        _cif_row_value(
                            row,
                            "_struct_conn.ptnr2_auth_seq_id",
                            "_struct_conn.ptnr2_label_seq_id",
                        )
                    )
                ),
                _cif_row_value(row, "_struct_conn.pdbx_ptnr2_PDB_ins_code"),
            )
        except (TypeError, ValueError):
            continue
        pairs.add((first, second))
    return pairs


def _explicit_covalent_links(
    source_text: str,
    *,
    source_format: str,
    selected_ligand: LigandInstance,
    receptor_protein: list[PdbAtom],
) -> list[str]:
    ligand_serials = {atom.serial for atom in selected_ligand.atoms}
    protein_serials = {atom.serial for atom in receptor_protein}
    links = [
        f"CONECT:{first}-{second}"
        for first, second in _conect_pairs(source_text)
        if (first in ligand_serials and second in protein_serials)
        or (second in ligand_serials and first in protein_serials)
    ]
    protein_residues = {atom.residue_key for atom in receptor_protein}
    residue_pairs = (
        _mmcif_covalent_residue_pairs(source_text)
        if source_format == "mmcif"
        else _pdb_link_residue_pairs(source_text)
    )
    for first, second in residue_pairs:
        if (first == selected_ligand.key and second in protein_residues) or (
            second == selected_ligand.key and first in protein_residues
        ):
            links.append(f"LINK:{first}-{second}")
    return sorted(links)


def _tokenize_cif(text: str) -> list[str]:
    tokens: list[str] = []
    lines = iter(text.splitlines())
    for line in lines:
        if line.startswith(";"):
            block = [line[1:]]
            for continuation in lines:
                if continuation.startswith(";"):
                    break
                block.append(continuation)
            tokens.append("\n".join(block))
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == "#":
            tokens.append("#")
            continue
        tokens.extend(shlex.split(stripped, comments=False, posix=True))
    return tokens


def _cif_loops(text: str) -> list[tuple[list[str], list[list[str]]]]:
    tokens = _tokenize_cif(text)
    loops: list[tuple[list[str], list[list[str]]]] = []
    index = 0
    while index < len(tokens):
        if tokens[index].lower() != "loop_":
            index += 1
            continue
        index += 1
        headers: list[str] = []
        while index < len(tokens) and tokens[index].startswith("_"):
            headers.append(tokens[index])
            index += 1
        if not headers:
            continue
        values: list[str] = []
        while index < len(tokens):
            token = tokens[index]
            if token == "#" or token.lower() == "loop_" or token.lower().startswith("data_"):
                break
            if token.startswith("_") and len(values) % len(headers) == 0:
                break
            values.append(token)
            index += 1
        rows = [
            values[start : start + len(headers)] for start in range(0, len(values), len(headers))
        ]
        rows = [row for row in rows if len(row) == len(headers)]
        loops.append((headers, rows))
    return loops


def _ccd_table(text: str, prefix: str) -> list[dict[str, str]]:
    for headers, rows in _cif_loops(text):
        if headers and all(header.startswith(prefix) for header in headers):
            return [dict(zip(headers, row)) for row in rows]
    raise ValueError(f"CCD table not found: {prefix}")


def _ccd_value(row: dict[str, str], suffix: str) -> str:
    key = next((name for name in row if name.endswith(suffix)), None)
    return row.get(key, "") if key else ""


def _bond_type(value: str) -> Chem.BondType:
    normalized = value.strip().upper()
    return {
        "SING": Chem.BondType.SINGLE,
        "SINGLE": Chem.BondType.SINGLE,
        "DOUB": Chem.BondType.DOUBLE,
        "DOUBLE": Chem.BondType.DOUBLE,
        "TRIP": Chem.BondType.TRIPLE,
        "TRIPLE": Chem.BondType.TRIPLE,
        "AROM": Chem.BondType.AROMATIC,
        "DELO": Chem.BondType.AROMATIC,
    }.get(normalized, Chem.BondType.SINGLE)


def write_native_ligand_sdf(
    ligand_atoms: list[PdbAtom],
    ccd_text: str,
    output: Path,
    *,
    title: str,
) -> dict[str, Any]:
    atom_rows = _ccd_table(ccd_text, "_chem_comp_atom.")
    bond_rows = _ccd_table(ccd_text, "_chem_comp_bond.")
    atom_definitions = {_ccd_value(row, ".atom_id"): row for row in atom_rows}
    deposited_names = {atom.atom_name for atom in ligand_atoms}
    missing_heavy_atoms = sorted(
        atom_name
        for atom_name, definition in atom_definitions.items()
        if (_ccd_value(definition, ".type_symbol") or "").upper() not in {"H", "D"}
        and atom_name not in deposited_names
    )
    if missing_heavy_atoms:
        raise ValueError(
            "native ligand is missing CCD heavy atoms: " + ",".join(missing_heavy_atoms)
        )
    molecule = Chem.RWMol()
    atom_indices: dict[str, int] = {}
    ordered_names: list[str] = []
    for pdb_atom in ligand_atoms:
        definition = atom_definitions.get(pdb_atom.atom_name)
        if definition is None:
            raise ValueError(f"CCD atom mapping missing for {pdb_atom.atom_name}")
        element = _ccd_value(definition, ".type_symbol") or pdb_atom.element
        atom = Chem.Atom(element.title())
        charge_text = _ccd_value(definition, ".charge")
        if charge_text not in {"", ".", "?"}:
            atom.SetFormalCharge(int(float(charge_text)))
        atom.SetProp("pdb_atom_name", pdb_atom.atom_name)
        atom_indices[pdb_atom.atom_name] = molecule.AddAtom(atom)
        ordered_names.append(pdb_atom.atom_name)
    for row in bond_rows:
        first = _ccd_value(row, ".atom_id_1")
        second = _ccd_value(row, ".atom_id_2")
        if first not in atom_indices or second not in atom_indices:
            continue
        bond_type = _bond_type(_ccd_value(row, ".value_order"))
        molecule.AddBond(atom_indices[first], atom_indices[second], bond_type)
        if bond_type == Chem.BondType.AROMATIC:
            molecule.GetAtomWithIdx(atom_indices[first]).SetIsAromatic(True)
            molecule.GetAtomWithIdx(atom_indices[second]).SetIsAromatic(True)
    native = molecule.GetMol()
    conformer = Chem.Conformer(len(ligand_atoms))
    conformer.Set3D(True)
    for index, pdb_atom in enumerate(ligand_atoms):
        conformer.SetAtomPosition(index, Point3D(pdb_atom.x, pdb_atom.y, pdb_atom.z))
    native.AddConformer(conformer, assignId=True)
    native.SetProp("_Name", title)
    native.SetProp("coordinate_source", "RCSB deposited model coordinates")
    native.SetProp("coordinate_frame", "same_as_clean_receptor_coordinates")
    native.SetProp("pdb_atom_names", json.dumps(ordered_names))
    sanitize_result = int(Chem.SanitizeMol(native, catchErrors=True))
    if sanitize_result:
        raise ValueError(f"CCD ligand topology failed RDKit sanitization: {sanitize_result}")
    output.parent.mkdir(parents=True, exist_ok=True)
    writer = Chem.SDWriter(str(output))
    writer.SetKekulize(False)
    writer.write(native)
    writer.close()
    restored = Chem.SDMolSupplier(str(output), removeHs=False, sanitize=False)[0]
    if restored is None or restored.GetNumAtoms() != len(ligand_atoms):
        raise ValueError("native ligand SDF round-trip failed")
    restored_conformer = restored.GetConformer()
    max_delta = 0.0
    for index, pdb_atom in enumerate(ligand_atoms):
        point = restored_conformer.GetAtomPosition(index)
        max_delta = max(
            max_delta,
            abs(point.x - pdb_atom.x),
            abs(point.y - pdb_atom.y),
            abs(point.z - pdb_atom.z),
        )
    return {
        "atoms": len(ligand_atoms),
        "bonds": native.GetNumBonds(),
        "sanitize_result": sanitize_result,
        "max_abs_coordinate_delta_A": round(max_delta, 6),
    }


def _centroid(atoms: list[PdbAtom]) -> list[float]:
    heavy = [atom for atom in atoms if atom.is_heavy] or atoms
    return [
        round(sum(getattr(atom, axis) for atom in heavy) / len(heavy), 4)
        for axis in ("x", "y", "z")
    ]


def prepare_native_structure(
    *,
    pdb_id: str,
    ligand_id: str,
    output_dir: Path,
    chains: Optional[list[str]] = None,
    ligand_chain: Optional[str] = None,
    ligand_resseq: Optional[int] = None,
    ligand_icode: Optional[str] = None,
    keep_hetero: Optional[list[str]] = None,
    model: int = 1,
    source_pdb: Optional[Path] = None,
    source_mmcif: Optional[Path] = None,
    ccd_cif: Optional[Path] = None,
    offline_replay: bool = False,
    http: Optional[CachedHttp] = None,
) -> dict[str, Any]:
    """Write a cleaned receptor and native ligand without changing deposited coordinates."""
    normalized_pdb = pdb_id.strip().upper()
    normalized_ligand = ligand_id.strip().upper()
    if not PDB_ID_PATTERN.fullmatch(normalized_pdb):
        raise ValueError("pdb_id must contain exactly four letters or digits")
    if not CCD_ID_PATTERN.fullmatch(normalized_ligand) or normalized_ligand in WATER_COMPONENTS:
        raise ValueError("a non-water ligand_id is required")
    if source_pdb and source_mmcif:
        raise ValueError("provide only one of source_pdb or source_mmcif")
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    client = http or CachedHttp(cache_only=offline_replay)
    source_urls: dict[str, str] = {}
    warnings: list[str] = []

    files: dict[str, Path] = {}
    if source_pdb:
        source_format = "pdb"
        source_text = Path(source_pdb).read_text(encoding="utf-8")
        source_coordinate_path = output_dir / "source" / f"{normalized_pdb}.pdb"
        complex_path = output_dir / "complex" / f"{normalized_pdb}_complex_original.pdb"
    elif source_mmcif:
        source_format = "mmcif"
        source_text = Path(source_mmcif).read_text(encoding="utf-8")
        source_coordinate_path = output_dir / "source" / f"{normalized_pdb}.cif"
        complex_path = output_dir / "complex" / f"{normalized_pdb}_complex_original.cif"
    else:
        source_format = "mmcif"
        cif_url = RCSB_CIF_URL.format(pdb_id=normalized_pdb)
        source_urls["mmcif"] = cif_url
        source_text = client.get_text(cif_url, cache_only=offline_replay)
        source_coordinate_path = output_dir / "source" / f"{normalized_pdb}.cif"
        complex_path = output_dir / "complex" / f"{normalized_pdb}_complex_original.cif"
    _write_text(source_coordinate_path, source_text)
    _write_text(complex_path, source_text)
    files["source_coordinates"] = source_coordinate_path
    files["complex_original_coordinates"] = complex_path

    if ccd_cif:
        ccd_text = Path(ccd_cif).read_text(encoding="utf-8")
    else:
        ccd_url = RCSB_CCD_URL.format(ligand_id=normalized_ligand)
        source_urls["ccd"] = ccd_url
        ccd_text = client.get_text(ccd_url, cache_only=offline_replay)
    ccd_path = output_dir / "source" / f"{normalized_ligand}_ccd.cif"
    _write_text(ccd_path, ccd_text)

    parsed_atoms = (
        parse_pdb_atoms(source_text, model=model)
        if source_format == "pdb"
        else parse_mmcif_atoms(source_text, model=model)
    )
    atoms = _select_altlocs(parsed_atoms)
    selected_chains = {chain.strip() for chain in chains or []}
    receptor_protein = [
        atom
        for atom in atoms
        if atom.record_type == "ATOM" and (not selected_chains or atom.chain in selected_chains)
    ]
    if not receptor_protein:
        raise ValueError("selected receptor chains contain no protein ATOM records")
    instances = _ligand_instances(atoms, receptor_protein, normalized_ligand)
    selected_ligand, selection_reason = _select_ligand_instance(
        instances,
        ligand_chain=ligand_chain.strip() if ligand_chain is not None else None,
        ligand_resseq=ligand_resseq,
        ligand_icode=ligand_icode.strip() if ligand_icode is not None else None,
    )
    ligand_atoms = list(selected_ligand.atoms)
    selected_serials = {atom.serial for atom in ligand_atoms}
    covalent_links = _explicit_covalent_links(
        source_text,
        source_format=source_format,
        selected_ligand=selected_ligand,
        receptor_protein=receptor_protein,
    )
    if covalent_links:
        raise ValueError(
            "selected ligand has an explicit covalent link to the target protein; "
            "use a dedicated covalent-complex preparation workflow: " + ";".join(covalent_links)
        )
    retained_hetero = {value.strip().upper() for value in keep_hetero or []}
    receptor_protein_indices = {atom.line_index for atom in receptor_protein}
    receptor_atoms = [
        atom
        for atom in atoms
        if (
            atom.line_index in receptor_protein_indices
            or (
                atom.record_type == "HETATM"
                and atom.residue_key != selected_ligand.key
                and atom.resname not in WATER_COMPONENTS
                and atom.resname in (PROTEIN_LIKE_HETERO | retained_hetero)
                and (
                    not selected_chains
                    or atom.chain in selected_chains
                    or atom.resname in retained_hetero
                )
            )
        )
    ]

    receptor_remarks = [
        f"SOURCE RCSB {normalized_pdb} MODEL {model}",
        "ATOM COORDINATES UNMODIFIED; WATER AND UNSELECTED HETERO REMOVED",
        f"SELECTED CHAINS {','.join(sorted(selected_chains)) if selected_chains else 'ALL'}",
    ]
    receptor_cif_path = output_dir / "receptor" / f"{normalized_pdb}_receptor_clean.cif"
    _write_text(
        receptor_cif_path,
        _mmcif_text(
            receptor_atoms,
            data_name=f"{normalized_pdb}_receptor_clean",
            remarks=receptor_remarks,
        ),
    )
    files["receptor_clean_mmcif"] = receptor_cif_path
    if all(_pdb_compatible(atom) for atom in receptor_atoms):
        receptor_pdb_path = output_dir / "receptor" / f"{normalized_pdb}_receptor_clean.pdb"
        _write_text(
            receptor_pdb_path,
            _pdb_text(receptor_atoms, remarks=receptor_remarks),
        )
        files["receptor_clean_pdb"] = receptor_pdb_path
    else:
        warnings.append("legacy_pdb_receptor_not_written:mmcif_required")
    ligand_key = selected_ligand.key
    ligand_stem = (
        f"{normalized_pdb}_{normalized_ligand}_{_safe_file_token(ligand_key[1])}_"
        f"{ligand_key[2]}{_safe_file_token(ligand_key[3]) if ligand_key[3] else ''}_native"
    )
    ligand_remarks = [
        f"EXTRACTED FROM RCSB {normalized_pdb} MODEL {model}",
        "NATIVE DEPOSITED COORDINATES; NO TRANSLATION ROTATION OR MINIMIZATION",
        f"RESIDUE {normalized_ligand} CHAIN {ligand_key[1] or 'blank'} "
        f"RESSEQ {ligand_key[2]}{ligand_key[3]}",
    ]
    ligand_cif_path = output_dir / "ligand" / f"{ligand_stem}.cif"
    _write_text(
        ligand_cif_path,
        _mmcif_text(
            ligand_atoms,
            data_name=ligand_stem,
            remarks=ligand_remarks,
        ),
    )
    files["ligand_native_mmcif"] = ligand_cif_path
    if all(_pdb_compatible(atom) for atom in ligand_atoms):
        ligand_pdb_path = output_dir / "ligand" / f"{ligand_stem}.pdb"
        _write_text(
            ligand_pdb_path,
            _pdb_text(
                ligand_atoms,
                remarks=ligand_remarks,
                conect_lines=(
                    _filtered_conect_lines(source_text, selected_serials)
                    if source_format == "pdb"
                    else []
                ),
            ),
        )
        files["ligand_native_pdb"] = ligand_pdb_path
    else:
        warnings.append("legacy_pdb_ligand_not_written:mmcif_and_sdf_required")
    ligand_sdf_path = output_dir / "ligand" / f"{ligand_stem}.sdf"
    sdf_validation = write_native_ligand_sdf(
        ligand_atoms,
        ccd_text,
        ligand_sdf_path,
        title=ligand_stem,
    )
    if sdf_validation["max_abs_coordinate_delta_A"] > 0.001:
        raise ValueError("native ligand SDF coordinates changed by more than 0.001 A")
    files["ligand_native_sdf"] = ligand_sdf_path

    instances_path = output_dir / "ligand_instances.csv"
    with instances_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "ligand_id",
                "chain",
                "resseq",
                "icode",
                "heavy_atom_count",
                "contact_atom_count_5A",
                "min_distance_A",
                "selected",
            ],
        )
        writer.writeheader()
        for instance in sorted(instances, key=lambda item: (item.key[1], item.key[2], item.key[3])):
            writer.writerow(
                {
                    "ligand_id": instance.key[0],
                    "chain": instance.key[1],
                    "resseq": instance.key[2],
                    "icode": instance.key[3],
                    "heavy_atom_count": instance.heavy_atom_count,
                    "contact_atom_count_5A": instance.contact_atom_count,
                    "min_distance_A": round(instance.min_distance_A, 4),
                    "selected": instance.key == selected_ligand.key,
                }
            )

    pocket_center = {
        "source": "native_ligand_heavy_atom_centroid",
        "pdb_id": normalized_pdb,
        "ligand_id": normalized_ligand,
        "ligand_instance": {
            "chain": ligand_key[1],
            "resseq": ligand_key[2],
            "icode": ligand_key[3],
        },
        "center_xyz_A": _centroid(ligand_atoms),
        "coordinate_frame": "same_as_source_complex_and_clean_receptor",
    }
    pocket_path = output_dir / "pocket_center.json"
    _write_text(pocket_path, json.dumps(pocket_center, ensure_ascii=False, indent=2))

    files.update(
        {
            "source_ccd_cif": ccd_path,
            "ligand_instances_csv": instances_path,
            "pocket_center_json": pocket_path,
        }
    )
    manifest = {
        "status": "ok",
        "pdb_id": normalized_pdb,
        "model": model,
        "source_coordinate_format": source_format,
        "selected_chains": sorted(selected_chains) if selected_chains else "all",
        "ligand_id": normalized_ligand,
        "selected_ligand_instance": {
            "chain": ligand_key[1],
            "resseq": ligand_key[2],
            "icode": ligand_key[3],
            "selection_reason": selection_reason,
            "heavy_atom_count": selected_ligand.heavy_atom_count,
            "contact_atom_count_5A": selected_ligand.contact_atom_count,
            "min_distance_A": round(selected_ligand.min_distance_A, 4),
        },
        "coordinate_validation": {
            "coordinate_extraction": "deposited model coordinates preserved numerically",
            "sdf_max_abs_coordinate_delta_A": sdf_validation["max_abs_coordinate_delta_A"],
            "same_coordinate_frame": True,
            "translation_or_rotation_applied": False,
            "minimization_applied": False,
        },
        "receptor_cleaning": {
            "protein_atom_count": sum(atom.record_type == "ATOM" for atom in receptor_atoms),
            "retained_hetero_atom_count": sum(
                atom.record_type == "HETATM" for atom in receptor_atoms
            ),
            "removed_water": True,
            "removed_selected_ligand": True,
            "retained_hetero_components": sorted(
                {atom.resname for atom in receptor_atoms if atom.record_type == "HETATM"}
            ),
            "hydrogens_added": False,
            "protonation_assigned": False,
            "note": "Coordinate cleaning only; run a validated protein-preparation backend before docking.",
        },
        "ligand_sdf": sdf_validation,
        "pocket_center": pocket_center,
        "source_urls": source_urls,
        "warnings": warnings,
        "files": {
            name: {
                "path": path.relative_to(output_dir).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for name, path in files.items()
        },
        "docking_ready_coordinates": True,
        "requires_protein_preparation": True,
    }
    manifest_path = output_dir / "structure_preparation_manifest.json"
    _write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest
