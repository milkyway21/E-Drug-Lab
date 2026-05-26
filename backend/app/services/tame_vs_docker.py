"""TAME-VS integration through Windows WSL Docker.

All TAME-VS execution is routed through:
    C:\\Windows\\System32\\wsl.exe [optional -d distro] docker ...

The service also converts TAME-VS CSV outputs into SDF files so the existing
SDF sync pipeline can import screened molecules into the molecule database.
"""
from __future__ import annotations

import csv
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rdkit import Chem
from sqlalchemy.orm import Session

from app.services.sdf_sync import sync_sdf_library


PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class TameVSCommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


class TameVSDockerRunner:
    def __init__(
        self,
        repo_path: str,
        image_name: str,
        output_dir: str,
        wsl_exe: str = r"C:\Windows\System32\wsl.exe",
        wsl_distro: Optional[str] = None,
        timeout: int = 600,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.image_name = image_name
        self.output_dir = Path(output_dir).resolve()
        self.wsl_exe = wsl_exe
        self.wsl_distro = wsl_distro
        self.timeout = timeout

    def status(self) -> dict:
        return {
            "wsl_exe": self.wsl_exe,
            "wsl_exe_exists": os.path.exists(self.wsl_exe),
            "wsl_distro": self.wsl_distro,
            "repo_path": str(self.repo_path),
            "repo_exists": self.repo_path.exists(),
            "dockerfile": str(self.repo_path / "Dockerfile.edrug"),
            "dockerfile_exists": (self.repo_path / "Dockerfile.edrug").exists(),
            "image_name": self.image_name,
            "output_dir": str(self.output_dir),
            "wsl_list": self._probe(["--list", "--verbose"]).to_dict(),
            "docker_version": self._docker(["--version"], timeout=30).to_dict(),
        }

    def build_image(self) -> TameVSCommandResult:
        dockerfile = self.repo_path / "Dockerfile.edrug"
        return self._docker(
            [
                "build",
                "-t",
                self.image_name,
                "-f",
                self._windows_to_wsl_path(dockerfile),
                self._windows_to_wsl_path(self.repo_path),
            ],
            timeout=max(self.timeout, 1800),
        )

    def run_library_preparation(self, input_csv: str, output_name: str, smiles_col: int = 2, compound_id_col: int = 1) -> TameVSCommandResult:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        input_path = Path(input_csv).resolve()
        return self._docker(
            [
                "run",
                "--rm",
                "-v",
                f"{self._windows_to_wsl_path(self.repo_path)}:/opt/tame-vs:ro",
                "-v",
                f"{self._windows_to_wsl_path(input_path.parent)}:/input:ro",
                "-v",
                f"{self._windows_to_wsl_path(self.output_dir)}:/work",
                self.image_name,
                "python",
                "/opt/tame-vs/5_Virtural_screening/Library_preparation.py",
                "-i",
                f"/input/{input_path.name}",
                "-s",
                str(smiles_col),
                "-c",
                str(compound_id_col),
                "-f",
                f"/work/{output_name}",
            ],
            timeout=self.timeout,
        )

    def create_smoke_input(self) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        input_csv = self.output_dir / "tame_vs_smoke_library.csv"
        with input_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["comp_id", "smiles"])
            writer.writeheader()
            writer.writerow({"comp_id": "aspirin", "smiles": "CC(=O)OC1=CC=CC=C1C(=O)O"})
            writer.writerow({"comp_id": "ibuprofen", "smiles": "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O"})
        return input_csv

    def run_smoke_test(self) -> dict:
        input_csv = self.create_smoke_input()
        result = self.run_library_preparation(str(input_csv), "tame_vs_smoke_morgan_1024_FP")
        return {
            "input_csv": str(input_csv),
            "fingerprint_csv": str(self.output_dir / "tame_vs_smoke_morgan_1024_FP.csv"),
            "command_result": result.to_dict(),
        }

    def ingest_result_csv(self, db: Session, result_csv: str, sdf_name: Optional[str] = None) -> dict:
        csv_path = Path(result_csv).resolve()
        if not csv_path.exists():
            raise FileNotFoundError(f"TAME-VS result CSV not found: {csv_path}")

        sdf_dir = PROJECT_ROOT / "molecules" / "sdf" / "tame_vs"
        sdf_dir.mkdir(parents=True, exist_ok=True)
        sdf_path = sdf_dir / (sdf_name or f"{csv_path.stem}.sdf")
        converted = csv_to_sdf(csv_path, sdf_path)
        sync_root = PROJECT_ROOT / "molecules" / "sdf"
        sync_result = sync_sdf_library(db, str(sync_root))
        return {
            "source_csv": str(csv_path),
            "sdf_path": str(sdf_path),
            "converted_molecules": converted,
            "sync_result": sync_result.to_dict(),
        }

    def _probe(self, args: list[str], timeout: int = 30) -> TameVSCommandResult:
        command = [self.wsl_exe, *args]
        return _run(command, timeout=timeout)

    def _docker(self, args: list[str], timeout: int) -> TameVSCommandResult:
        command = [self.wsl_exe]
        if self.wsl_distro:
            command.extend(["-d", self.wsl_distro])
        command.extend(["docker", *args])
        return _run(command, timeout=timeout)

    def compose(self, package_path: str | Path, args: list[str], timeout: Optional[int] = None) -> TameVSCommandResult:
        package_dir = Path(package_path).resolve()
        command = [self.wsl_exe]
        if self.wsl_distro:
            command.extend(["-d", self.wsl_distro])
        command.extend(
            [
                "bash",
                "-lc",
                f"cd {sh_quote(self._windows_to_wsl_path(package_dir))} && docker compose {' '.join(sh_quote(arg) for arg in args)}",
            ]
        )
        return _run(command, timeout=timeout or self.timeout)

    def _windows_to_wsl_path(self, path: Path) -> str:
        drive = path.drive.rstrip(":").lower()
        rest = path.as_posix().split(":", 1)[-1].lstrip("/")
        return f"/mnt/{drive}/{rest}"


def csv_to_sdf(csv_path: Path, sdf_path: Path) -> int:
    rows = list(csv.DictReader(csv_path.open("r", encoding="utf-8-sig")))
    writer = Chem.SDWriter(str(sdf_path))
    converted = 0
    try:
        for row in rows:
            smiles = (
                row.get("smiles")
                or row.get("SMILES")
                or row.get("Molecule (RDKit Mol)")
                or row.get("canonical_smiles")
            )
            if not smiles:
                continue
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                continue
            name = row.get("comp_id") or row.get("Catalog ID") or row.get("molecule_chembl_id") or f"tame_vs_{converted + 1}"
            mol.SetProp("_Name", name)
            mol.SetProp("Catalog ID", name)
            for key, value in row.items():
                if value is not None and value != "":
                    mol.SetProp(str(key), str(value))
            writer.write(mol)
            converted += 1
    finally:
        writer.close()
    return converted


def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _run(command: list[str], timeout: int) -> TameVSCommandResult:
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return TameVSCommandResult(command, proc.returncode, proc.stdout or "", proc.stderr or "")
    except FileNotFoundError as exc:
        return TameVSCommandResult(command, 127, "", str(exc))
    except subprocess.TimeoutExpired as exc:
        return TameVSCommandResult(command, 124, exc.stdout or "", exc.stderr or f"Timed out after {timeout}s")
