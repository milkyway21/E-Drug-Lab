"""Tests for SMILES-based Vina docking preparation."""
from pathlib import Path

import pytest

from app.services.docking_prep import (
    estimate_pocket_box,
    resolve_receptor_pdb,
    resolve_vina_executable,
)


def test_resolve_vina_executable_finds_conda_binary():
    path = resolve_vina_executable(None)
    if path:
        assert Path(path).is_file()


def test_resolve_receptor_pdb_from_targets_dir():
    pdb = resolve_receptor_pdb(target_pdb_id="4hhb")
    assert pdb.is_file()
    assert pdb.suffix.lower() == ".pdb"


def test_estimate_pocket_box_from_pdb():
    pdb = resolve_receptor_pdb(target_pdb_id="4hhb")
    box = estimate_pocket_box(pdb)
    assert box.size_x > 0
    assert abs(box.center_x) < 500
