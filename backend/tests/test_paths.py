"""Tests for lab-safe path helpers."""
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.core.paths import (
    ensure_safe_path,
    get_repo_root,
    is_safe_path,
    safe_upload_filename,
    validate_pdb_id,
)


def test_validate_pdb_id_ok():
    assert validate_pdb_id("4HHB") == "4hhb"


def test_validate_pdb_id_rejects_traversal():
    with pytest.raises(AppError) as exc:
        validate_pdb_id("../etc/passwd")
    assert exc.value.code == "INVALID_PDB_ID"


def test_safe_upload_filename_strips_path():
    assert safe_upload_filename("../../etc/passwd", "x.pdb") == "passwd"


def test_ensure_safe_path_under_repo():
    repo = get_repo_root()
    p = ensure_safe_path(str(repo / "molecules"), must_exist=True)
    assert p.is_dir()


def test_ensure_safe_path_rejects_system_file():
    with pytest.raises(AppError) as exc:
        ensure_safe_path("/etc/passwd", must_exist=False)
    assert exc.value.code == "PATH_NOT_ALLOWED"


def test_is_safe_path_data_ye():
    assert is_safe_path("/data/ye")
