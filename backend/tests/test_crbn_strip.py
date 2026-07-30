"""CRBN 锚定整体切除单测。"""
from __future__ import annotations

import pytest

from app.pipelines.vav1_rl.crbn_strip import (
    has_glutarimide,
    strip_crbn_anchor_module,
    strip_smiles_or_raise,
)
from rdkit import Chem


@pytest.mark.parametrize(
    "smi,expect_mode",
    [
        # C-linked ortho Cl
        ("CCc1cc(-c2cccc(C3CCC(=O)NC3=O)c2Cl)ccc1N", "C_orthoCl"),
        ("Nc1nccn1Cc1ccc(-c2cccc(C3CCC(=O)NC3=O)c2Cl)cc1", "C_orthoCl"),
        ("O=C1CCC(c2cccc(-c3ccc(OCc4ccccn4)cc3)c2Cl)C(=O)N1", "C_orthoCl"),
        # no anchor (decoy-like)
        ("CCO", "no_anchor"),
        ("c1ccccc1", "no_anchor"),
    ],
)
def test_strip_modes(smi, expect_mode):
    r = strip_crbn_anchor_module(smi)
    assert r["ok"] is True
    assert r["strip_mode"] == expect_mode
    assert r["smiles_stripped"]
    if expect_mode != "no_anchor":
        mol = Chem.MolFromSmiles(r["smiles_stripped"])
        assert mol is not None
        assert not has_glutarimide(mol)
        assert mol.GetNumHeavyAtoms() >= 5


def test_strip_removes_glutarimide():
    smi = "CN1CCN(CCOc2ccc(-c3cccc(C4CCC(=O)NC4=O)c3Cl)cc2)CC1"
    r = strip_crbn_anchor_module(smi)
    assert r["ok"]
    assert r["had_glutarimide"]
    assert not has_glutarimide(Chem.MolFromSmiles(r["smiles_stripped"]))


def test_invalid_smiles():
    r = strip_crbn_anchor_module("not_a_smiles")
    assert r["ok"] is False
    assert r["error"] == "invalid_smiles"


def test_strip_smiles_or_raise():
    out = strip_smiles_or_raise("c1ccccc1")
    assert out == "c1ccccc1"
    with pytest.raises(ValueError):
        strip_smiles_or_raise("%%%")
