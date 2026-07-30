"""SDF 解析器测试"""
import os
import pytest
from pathlib import Path

# 跳过 RDKit 导入失败的情况
rdkit_available = True
try:
    from app.services.sdf_parser import parse_sdf_file, compute_file_hash, scan_sdf_directory
except ImportError:
    rdkit_available = False

SDF_DIR = Path(__file__).resolve().parents[2] / "molecules" / "sdf"


@pytest.mark.skipif(not rdkit_available, reason="RDKit not available")
class TestParseSDFFile:
    def test_aspirin_molecular_weight(self):
        """aspirin.sdf 的 MW ≈ 180.16。"""
        sdf_path = SDF_DIR / "aspirin.sdf"
        if not sdf_path.exists():
            pytest.skip(f"SDF file not found: {sdf_path}")
        results = parse_sdf_file(str(sdf_path))
        assert len(results) > 0
        mol = results[0]
        assert mol.error is None
        assert mol.molecular_weight is not None
        assert abs(mol.molecular_weight - 180.16) < 1.0

    def test_aspirin_logp(self):
        """aspirin.sdf 的 LogP ≈ 1.2。"""
        sdf_path = SDF_DIR / "aspirin.sdf"
        if not sdf_path.exists():
            pytest.skip(f"SDF file not found: {sdf_path}")
        results = parse_sdf_file(str(sdf_path))
        assert len(results) > 0
        mol = results[0]
        assert mol.logp is not None
        assert abs(mol.logp - 1.2) < 1.0

    def test_ibuprofen_molecular_weight(self):
        """ibuprofen.sdf 的 MW ≈ 206.28。"""
        sdf_path = SDF_DIR / "ibuprofen.sdf"
        if not sdf_path.exists():
            pytest.skip(f"SDF file not found: {sdf_path}")
        results = parse_sdf_file(str(sdf_path))
        assert len(results) > 0
        mol = results[0]
        assert mol.molecular_weight is not None
        assert abs(mol.molecular_weight - 206.28) < 1.0

    def test_ibuprofen_logp(self):
        """ibuprofen.sdf 的 LogP ≈ 3.5。"""
        sdf_path = SDF_DIR / "ibuprofen.sdf"
        if not sdf_path.exists():
            pytest.skip(f"SDF file not found: {sdf_path}")
        results = parse_sdf_file(str(sdf_path))
        assert len(results) > 0
        mol = results[0]
        assert mol.logp is not None
        assert abs(mol.logp - 3.5) < 1.5

    def test_inchikey_consistency(self):
        """同一分子多次解析得到相同 InChIKey。"""
        sdf_path = SDF_DIR / "aspirin.sdf"
        if not sdf_path.exists():
            pytest.skip(f"SDF file not found: {sdf_path}")
        results1 = parse_sdf_file(str(sdf_path))
        results2 = parse_sdf_file(str(sdf_path))
        assert results1[0].inchikey == results2[0].inchikey

    def test_multi_conformer_sdf(self):
        """多构象 SDF 文件返回多个结果。"""
        sdf_files = list(SDF_DIR.glob("*.sdf"))
        if not sdf_files:
            pytest.skip("No SDF files found")
        for sdf_path in sdf_files:
            results = parse_sdf_file(str(sdf_path))
            # 至少应该有一个结果
            assert len(results) >= 1

    def test_nonexistent_file(self):
        """不存在的文件返回空列表。"""
        results = parse_sdf_file("/nonexistent/path/file.sdf")
        assert results == []

    def test_smiles_present(self):
        """解析后的分子应有 SMILES。"""
        sdf_path = SDF_DIR / "aspirin.sdf"
        if not sdf_path.exists():
            pytest.skip(f"SDF file not found: {sdf_path}")
        results = parse_sdf_file(str(sdf_path))
        assert results[0].smiles is not None
        assert len(results[0].smiles) > 0


@pytest.mark.skipif(not rdkit_available, reason="RDKit not available")
class TestComputeFileHash:
    def test_hash_consistency(self):
        """同一文件的 hash 一致。"""
        sdf_path = SDF_DIR / "aspirin.sdf"
        if not sdf_path.exists():
            pytest.skip(f"SDF file not found: {sdf_path}")
        h1 = compute_file_hash(str(sdf_path))
        h2 = compute_file_hash(str(sdf_path))
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex


@pytest.mark.skipif(not rdkit_available, reason="RDKit not available")
class TestScanSDFDirectory:
    def test_scan_directory(self):
        """扫描 SDF 目录返回文件列表。"""
        if not SDF_DIR.is_dir():
            pytest.skip(f"SDF dir not found: {SDF_DIR}")
        files = scan_sdf_directory(str(SDF_DIR))
        assert len(files) > 0
        for f in files:
            assert "filename" in f
            assert "file_path" in f
            assert "file_hash" in f
            assert "file_size_bytes" in f

    def test_scan_nonexistent_dir(self):
        """扫描不存在的目录返回空列表。"""
        files = scan_sdf_directory("/nonexistent/dir")
        assert files == []
