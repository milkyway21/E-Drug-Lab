"""TAME-VS 2.0 integration through Windows WSL Docker.

All TAME-VS execution is routed through:
    C:\\Windows\\System32\\wsl.exe [optional -d distro] docker ...

The service also converts TAME-VS CSV outputs into SDF files so the existing
SDF sync pipeline can import screened molecules into the molecule database.
"""
from __future__ import annotations

import csv
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
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
        package_path: str,
        service_url: str = "http://localhost:8000",
        wsl_exe: str = r"C:\Windows\System32\wsl.exe",
        wsl_distro: Optional[str] = None,
        timeout: int = 1800,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.image_name = image_name
        self.output_dir = Path(output_dir).resolve()
        self.package_path = Path(package_path).resolve()
        self.service_url = service_url.rstrip("/")
        self.wsl_exe = wsl_exe
        self.wsl_distro = wsl_distro
        self.timeout = timeout

    def status(self) -> dict:
        docker_available = self._check_docker_available()

        # Check service health if possible
        service_healthy = False
        service_status = {}
        try:
            response = requests.get(f"{self.service_url}/health", timeout=5)
            if response.status_code == 200:
                service_healthy = True
                service_status = response.json()
        except Exception:
            pass

        return {
            "status": "running" if service_healthy else ("available" if docker_available else "unavailable"),
            "version": "2.0.0",
            "docker_available": docker_available,
            "service_healthy": service_healthy,
            "service_status": service_status,
            "wsl_exe": self.wsl_exe,
            "wsl_exe_exists": os.path.exists(self.wsl_exe),
            "wsl_distro": self.wsl_distro,
            "repo_path": str(self.repo_path),
            "repo_exists": self.repo_path.exists(),
            "package_path": str(self.package_path),
            "package_exists": self.package_path.exists(),
            "service_url": self.service_url,
        }

    def _check_docker_available(self) -> bool:
        try:
            result = self._docker(["--version"], timeout=30)
            return result.returncode == 0 and "Docker" in result.stdout
        except Exception:
            return False

    def build_image(self) -> TameVSCommandResult:
        dockerfile = self.package_path / "Dockerfile"
        return self._docker(
            [
                "build",
                "-t",
                "target-driven-vs-api:latest",
                "-f",
                self._windows_to_wsl_path(dockerfile),
                self._windows_to_wsl_path(self.package_path),
            ],
            timeout=max(self.timeout, 3600),
        )

    def start_service(self) -> TameVSCommandResult:
        return self.compose(["up", "-d"])

    def stop_service(self) -> TameVSCommandResult:
        return self.compose(["down"])

    def restart_service(self) -> TameVSCommandResult:
        self.stop_service()
        time.sleep(2)
        return self.start_service()

    def compose(self, args: list[str]) -> TameVSCommandResult:
        command = [self.wsl_exe]
        if self.wsl_distro:
            command.extend(["-d", self.wsl_distro])
        command.extend(
            [
                "bash",
                "-lc",
                f"cd {self._windows_to_wsl_path(self.package_path)} && docker compose {' '.join(self._sh_quote(arg) for arg in args)}",
            ]
        )
        return self._run(command, timeout=self.timeout)

    def run_smoke_test(self, db: Optional[Session] = None) -> dict:
        """Run a quick smoke test via the API service"""
        # First ensure service is up
        try:
            health = requests.get(f"{self.service_url}/health", timeout=10)
            if health.status_code != 200:
                self.start_service()
                time.sleep(10)
        except Exception:
            self.start_service()
            time.sleep(10)

        try:
            response = requests.post(
                f"{self.service_url}/inference",
                json={
                    "task": "smoke_test",
                    "output_name": "smoke_test",
                    "preview_rows": 20,
                },
                timeout=self.timeout,
            )
            if response.status_code != 200:
                return {
                    "error": f"API returned {response.status_code}",
                    "detail": response.text,
                }
            result = response.json()

            # Copy the result CSV to our output dir and convert to SDF
            if "score_csv" in result:
                # Extract CSV from container
                csv_name = Path(result["score_csv"]).name
                csv_path = self.output_dir / csv_name
                self._copy_from_container("target-driven-vs-api", result["score_csv"], str(csv_path))

                # Convert to SDF and ingest
                ingest_result = self.ingest_result_csv(db, str(csv_path), "tame_vs_smoke.sdf")
                result["ingest"] = ingest_result

            return result
        except Exception as e:
            # Fallback to original smoke test if API not available
            return self._fallback_smoke_test(str(e), db)

    def run_full_50k_screen(
        self,
        top_percent: float = 1.0,
        target_pdb_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> dict:
        """Run virtual screening on full Enamine 50K library"""
        output_name = f"{target_pdb_id or 'screen'}_50k"

        # Ensure service is up
        try:
            health = requests.get(f"{self.service_url}/health", timeout=10)
            if health.status_code != 200:
                self.start_service()
                time.sleep(15)
        except Exception:
            self.start_service()
            time.sleep(15)

        try:
            response = requests.post(
                f"{self.service_url}/inference",
                json={
                    "task": "full_50k_screen",
                    "output_name": output_name,
                    "top_percent": top_percent,
                    "preview_rows": 100,
                },
                timeout=3600,  # Longer timeout for full screen
            )
            if response.status_code != 200:
                return {
                    "error": f"API returned {response.status_code}",
                    "detail": response.text,
                }
            result = response.json()

            if "top_csv" in result:
                # Extract CSV from container
                csv_name = Path(result["top_csv"]).name
                csv_path = self.output_dir / csv_name
                self._copy_from_container("target-driven-vs-api", result["top_csv"], str(csv_path))

                # Convert to SDF and ingest
                sdf_name = f"{output_name}_top{int(top_percent)}percent.sdf"
                ingest_result = self.ingest_result_csv(db, str(csv_path), sdf_name)
                result["ingest"] = ingest_result

            return result
        except Exception as e:
            return {"error": str(e)}

    def _copy_from_container(self, container_name: str, container_path: str, local_path: str) -> None:
        """Copy a file from container to local"""
        command = [self.wsl_exe]
        if self.wsl_distro:
            command.extend(["-d", self.wsl_distro])
        command.extend([
            "docker", "cp",
            f"{container_name}:{container_path}",
            self._windows_to_wsl_path(Path(local_path)),
        ])
        self._run(command, timeout=300)

    def _fallback_smoke_test(self, error_msg: str, db: Optional[Session] = None) -> dict:
        """Original smoke test as fallback"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        input_csv = self.output_dir / "tame_vs_smoke_library.csv"
        with input_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["comp_id", "smiles"])
            writer.writeheader()
            writer.writerow({"comp_id": "aspirin", "smiles": "CC(=O)OC1=CC=CC=C1C(=O)O"})
            writer.writerow({"comp_id": "ibuprofen", "smiles": "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O"})

        result = self.run_library_preparation(str(input_csv), "tame_vs_smoke_morgan_1024_FP")

        out = {
            "input_csv": str(input_csv),
            "fingerprint_csv": str(self.output_dir / "tame_vs_smoke_morgan_1024_FP.csv"),
            "command_result": result.to_dict(),
            "fallback": error_msg,
        }

        # Ingest
        ingest_result = self.ingest_result_csv(
            db,
            str(self.output_dir / "tame_vs_smoke_morgan_1024_FP.csv"),
        )
        out["ingest"] = ingest_result
        return out

    def run_library_preparation(self, input_csv: str, output_name: str, smiles_col: int = 1, compound_id_col: int = 2) -> TameVSCommandResult:
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
                "target-driven-vs-api:latest",
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

    def ingest_result_csv(self, db: Optional[Session], result_csv: str, sdf_name: Optional[str] = None) -> dict:
        csv_path = Path(result_csv).resolve()
        if not csv_path.exists():
            raise FileNotFoundError(f"TAME-VS result CSV not found: {csv_path}")

        sdf_dir = PROJECT_ROOT / "molecules" / "sdf" / "tame_vs"
        sdf_dir.mkdir(parents=True, exist_ok=True)
        sdf_path = sdf_dir / (sdf_name or f"{csv_path.stem}.sdf")
        converted = csv_to_sdf(csv_path, sdf_path)

        sync_result = None
        if db:
            sync_root = PROJECT_ROOT / "molecules" / "sdf"
            sync_result = sync_sdf_library(db, str(sync_root))

        return {
            "source_csv": str(csv_path),
            "sdf_path": str(sdf_path),
            "converted_molecules": converted,
            "sync_result": sync_result.to_dict() if sync_result else None,
        }

    def _probe(self, args: list[str], timeout: int = 30) -> TameVSCommandResult:
        command = [self.wsl_exe, *args]
        return self._run(command, timeout=timeout)

    def _docker(self, args: list[str], timeout: int) -> TameVSCommandResult:
        command = [self.wsl_exe]
        if self.wsl_distro:
            command.extend(["-d", self.wsl_distro])
        command.extend(["docker", *args])
        return self._run(command, timeout=timeout)

    def _windows_to_wsl_path(self, path: Path) -> str:
        drive = path.drive.rstrip(":").lower()
        rest = path.as_posix().split(":", 1)[-1].lstrip("/")
        return f"/mnt/{drive}/{rest}"

    def _sh_quote(self, value: str) -> str:
        return "'" + value.replace("'", "'\"'\"'") + "'"

    def _run(self, command: list[str], timeout: int) -> TameVSCommandResult:
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


def csv_to_sdf(csv_path: Path, sdf_path: Path) -> int:
    rows = list(csv.DictReader(csv_path.open("r", encoding="utf-8-sig")))
    if not rows:
        return 0
    writer = Chem.SDWriter(str(sdf_path))
    converted = 0
    try:
        for row in rows:
            # Try multiple possible column names for smiles
            smiles = None
            for key in ["smiles", "SMILES", "Molecule (RDKit Mol)", "canonical_smiles"]:
                if key in row and row[key]:
                    smiles = row[key]
                    break

            if not smiles:
                continue

            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                continue

            # Try multiple possible column names for id
            compound_id = None
            for key in ["comp_id", "Catalog ID", "molecule_chembl_id"]:
                if key in row and row[key]:
                    compound_id = row[key]
                    break

            if not compound_id:
                compound_id = f"tame_vs_{converted + 1}"

            mol.SetProp("_Name", compound_id)
            mol.SetProp("Catalog ID", compound_id)

            # Copy all other properties
            for key, value in row.items():
                if value is not None and value != "":
                    try:
                        mol.SetProp(str(key), str(value))
                    except Exception:
                        pass

            writer.write(mol)
            converted += 1
    finally:
        writer.close()

    # Clean up if no molecules
    if converted == 0 and sdf_path.exists():
        sdf_path.unlink()

    return converted
