"""DrugCLIP Docker integration through WSL2.

All DrugCLIP execution is routed through Docker containers managed via:
    C:\\Windows\\System32\\wsl.exe [optional -d distro] docker ...

The service converts SDF + PDB inputs to LMDB format, runs DrugCLIP screening
via the containerized FastAPI service, and returns ranked molecules.
"""
from __future__ import annotations

import json
import os
import shutil
import ssl
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrllibRequest, urlopen

from rdkit import Chem
from sqlalchemy.orm import Session

from app.core.paths import get_repo_root
from app.services.sdf_sync import sync_sdf_library

PROJECT_ROOT = get_repo_root()

SMOKE_MOLECULES = [
    ("aspirin", "CC(=O)OC1=CC=CC=C1C(=O)O"),
    ("ibuprofen", "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O"),
    ("caffeine", "CN1C=NC2=C1C(=O)N(C(=O)N2C)C"),
]


@dataclass
class DrugClipCommandResult:
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


class DrugClipDockerRunner:
    def __init__(
        self,
        package_path: str,
        image_name: str,
        service_url: str,
        output_dir: str,
        wsl_exe: str = r"C:\Windows\System32\wsl.exe",
        wsl_distro: Optional[str] = None,
        timeout: int = 600,
    ):
        self.package_path = Path(package_path).resolve()
        self.image_name = image_name
        self.service_url = service_url.rstrip("/")
        self.output_dir = Path(output_dir).resolve()
        self.wsl_exe = wsl_exe
        self.wsl_distro = wsl_distro
        self.timeout = timeout

    def status(self) -> dict:
        docker_available = self._check_docker_available()
        service_healthy = False
        service_status: dict = {}
        try:
            with urlopen(f"{self.service_url}/health", timeout=5) as resp:
                if resp.status == 200:
                    service_healthy = True
                    service_status = json.loads(resp.read().decode())
        except Exception:
            pass

        return {
            "status": "running" if service_healthy else ("available" if docker_available else "unavailable"),
            "version": "1.0.0",
            "docker_available": docker_available,
            "service_healthy": service_healthy,
            "service_status": service_status,
            "wsl_exe": self.wsl_exe,
            "wsl_exe_exists": os.path.exists(self.wsl_exe),
            "wsl_distro": self.wsl_distro,
            "package_path": str(self.package_path),
            "package_exists": self.package_path.exists(),
            "image_name": self.image_name,
            "service_url": self.service_url,
            "output_dir": str(self.output_dir),
        }

    def _check_docker_available(self) -> bool:
        try:
            result = _docker(self.wsl_exe, self.wsl_distro, ["--version"], timeout=30)
            return result.returncode == 0 and "Docker" in result.stdout
        except Exception:
            return False

    def start_service(self) -> DrugClipCommandResult:
        return self.compose(["up", "-d"], timeout=1800)

    def stop_service(self) -> DrugClipCommandResult:
        return self.compose(["down"], timeout=600)

    def ensure_service(self) -> None:
        try:
            with urlopen(f"{self.service_url}/health", timeout=10):
                return
        except Exception:
            pass
        result = self.start_service()
        if result.returncode != 0:
            raise RuntimeError(f"Failed to start DrugCLIP service: {result.stderr or result.stdout}")
        for _ in range(30):
            try:
                with urlopen(f"{self.service_url}/health", timeout=5):
                    return
            except Exception:
                time.sleep(2)
        raise RuntimeError("DrugCLIP service did not become healthy after start")

    def compose(self, args: list[str], timeout: Optional[int] = None) -> DrugClipCommandResult:
        command = [self.wsl_exe]
        if self.wsl_distro:
            command.extend(["-d", self.wsl_distro])
        command.extend([
            "bash", "-lc",
            f"cd {_sh_quote(self._to_wsl_path(self.package_path))} && "
            f"docker compose {' '.join(_sh_quote(a) for a in args)}",
        ])
        return _run(command, timeout=timeout or self.timeout)

    def build_image(self) -> DrugClipCommandResult:
        return _docker(
            self.wsl_exe, self.wsl_distro,
            ["build", "-t", self.image_name,
             self._to_wsl_path(self.package_path)],
            timeout=max(self.timeout, 1800),
        )

    def work_dir(self) -> Path:
        work = self.package_path / "work"
        work.mkdir(parents=True, exist_ok=True)
        return work

    def stage_inputs(self, sdf_path: Path, pdb_path: Path, prefix: str = "run") -> dict:
        """Copy host files into package work/ and return container paths."""
        work = self.work_dir()
        staged_sdf = work / f"{prefix}.sdf"
        staged_pdb = work / f"{prefix}.pdb"
        shutil.copy2(sdf_path, staged_sdf)
        shutil.copy2(pdb_path, staged_pdb)
        return {
            "sdf_path": str(staged_sdf),
            "pocket_pdb_path": str(staged_pdb),
            "container_sdf_path": f"/app/work/{staged_sdf.name}",
            "container_pdb_path": f"/app/work/{staged_pdb.name}",
        }

    def write_sample_sdf(self, path: Path) -> int:
        writer = Chem.SDWriter(str(path))
        count = 0
        try:
            for name, smiles in SMOKE_MOLECULES:
                mol = Chem.MolFromSmiles(smiles)
                if mol is None:
                    continue
                mol.SetProp("_Name", name)
                writer.write(mol)
                count += 1
        finally:
            writer.close()
        return count

    def resolve_pdb(self, pdb_id: str) -> Path:
        pdb_id = pdb_id.strip().upper()
        work = self.work_dir()
        staged = work / f"{pdb_id.lower()}.pdb"
        if staged.exists():
            return staged

        for candidate in (
            PROJECT_ROOT / "backend" / "data" / "targets" / f"{pdb_id.lower()}.pdb",
            Path("data/targets") / f"{pdb_id.lower()}.pdb",
        ):
            if candidate.exists():
                shutil.copy2(candidate, staged)
                return staged

        repo_pdb = PROJECT_ROOT / "molecules" / "pdb" / f"{pdb_id}.pdb"
        if repo_pdb.exists():
            shutil.copy2(repo_pdb, staged)
            return staged

        data = self._download_pdb(pdb_id)
        staged.write_bytes(data)
        return staged

    def _download_pdb(self, pdb_id: str) -> bytes:
        pdb_id = pdb_id.lower()
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        last_error: Optional[Exception] = None
        for protocol in ("https", "http"):
            url = f"{protocol}://files.rcsb.org/download/{pdb_id}.pdb"
            try:
                return urlopen(url, timeout=30, context=ctx).read()
            except Exception as exc:
                last_error = exc
        raise FileNotFoundError(f"Cannot download PDB {pdb_id.upper()}: {last_error}")

    def screen(
        self,
        sdf_path: str,
        pocket_pdb_path: str,
        top_k: int = 100,
        pocket_center: Optional[list[float]] = None,
        pocket_radius: float = 10.0,
    ) -> dict:
        payload: dict = {
            "sdf_path": sdf_path,
            "pocket_pdb_path": pocket_pdb_path,
            "top_k": top_k,
        }
        if pocket_center:
            payload["pocket_center"] = pocket_center
            payload["pocket_radius"] = pocket_radius

        req = UrllibRequest(
            f"{self.service_url}/screen",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as exc:
            detail = exc.read().decode() if exc.fp else str(exc)
            return {"ok": False, "error": str(exc), "detail": detail, "status_code": exc.code}
        except URLError as exc:
            return {"ok": False, "error": str(exc)}

    def run_smoke_test(self, db: Optional[Session] = None) -> dict:
        self.ensure_service()
        work = self.work_dir()
        sample_sdf = work / "smoke_library.sdf"
        if self.write_sample_sdf(sample_sdf) == 0:
            return {"ok": False, "error": "Failed to build smoke SDF"}

        pdb_path = self.resolve_pdb("4HHB")
        staged = self.stage_inputs(sample_sdf, pdb_path, prefix="smoke")
        screening = self.screen(
            staged["container_sdf_path"],
            staged["container_pdb_path"],
            top_k=min(10, len(SMOKE_MOLECULES)),
        )
        if not screening.get("ok"):
            return {"ok": False, "screening": screening}

        ingest = self.ingest_results(db, screening.get("results") or [], "drugclip_smoke.sdf")
        return {"ok": True, "screening": screening, "ingest": ingest}

    def run_pipeline_screen(
        self,
        target_pdb_id: str,
        top_k: int = 10,
        db: Optional[Session] = None,
        auto_ingest: bool = True,
    ) -> dict:
        self.ensure_service()
        work = self.work_dir()
        sample_sdf = work / "pipeline_library.sdf"
        if self.write_sample_sdf(sample_sdf) == 0:
            return {"ok": False, "error": "Failed to build pipeline SDF"}

        pdb_path = self.resolve_pdb(target_pdb_id)
        staged = self.stage_inputs(sample_sdf, pdb_path, prefix=f"pipeline_{target_pdb_id.lower()}")
        screening = self.screen(
            staged["container_sdf_path"],
            staged["container_pdb_path"],
            top_k=top_k,
        )
        if not screening.get("ok"):
            return {"ok": False, "screening": screening}

        ingest = None
        if auto_ingest:
            sdf_name = f"drugclip_pipeline_{target_pdb_id.lower()}.sdf"
            ingest = self.ingest_results(db, screening.get("results") or [], sdf_name)

        return {
            "ok": True,
            "target_pdb_id": target_pdb_id.upper(),
            "screening": screening,
            "ingest": ingest,
        }

    def ingest_results(
        self,
        db: Optional[Session],
        results: list[dict],
        sdf_name: str,
    ) -> dict:
        sdf_result = self.results_to_sdf(results, sdf_name)
        sync_result = None
        if db is not None and sdf_result.get("converted_molecules", 0) > 0:
            sync_root = PROJECT_ROOT / "molecules" / "sdf"
            sync_result = sync_sdf_library(db, str(sync_root))
        sdf_result["sync_result"] = sync_result.to_dict() if sync_result else None
        return sdf_result

    def results_to_sdf(self, results: list[dict], sdf_name: str) -> dict:
        """Convert DrugCLIP ranking results to SDF."""
        sdf_dir = PROJECT_ROOT / "molecules" / "sdf" / "drugclip"
        sdf_dir.mkdir(parents=True, exist_ok=True)
        sdf_path = sdf_dir / sdf_name

        writer = Chem.SDWriter(str(sdf_path))
        converted = 0
        try:
            for item in results:
                name = item.get("name", f"drugclip_{converted + 1}")
                score = item.get("score", 0.0)
                smiles = item.get("smiles")
                mol = Chem.MolFromSmiles(smiles) if smiles else None
                if mol is None:
                    for candidate_name, candidate_smiles in SMOKE_MOLECULES:
                        if candidate_name == name:
                            mol = Chem.MolFromSmiles(candidate_smiles)
                            break
                if mol is None:
                    mol = Chem.MolFromSmiles(name)
                if mol is None:
                    continue
                mol.SetProp("_Name", name)
                mol.SetProp("DrugClip_Score", str(round(float(score), 6)))
                writer.write(mol)
                converted += 1
        finally:
            writer.close()

        if converted == 0 and sdf_path.exists():
            sdf_path.unlink()

        return {
            "sdf_path": str(sdf_path),
            "converted_molecules": converted,
        }

    def _to_wsl_path(self, path: Path) -> str:
        drive = path.drive.rstrip(":").lower()
        rest = path.as_posix().split(":", 1)[-1].lstrip("/")
        return f"/mnt/{drive}/{rest}"


def _docker(wsl_exe: str, wsl_distro: Optional[str], args: list[str], timeout: int) -> DrugClipCommandResult:
    command = [wsl_exe]
    if wsl_distro:
        command.extend(["-d", wsl_distro])
    command.extend(["docker", *args])
    return _run(command, timeout=timeout)


def _sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _run(command: list[str], timeout: int) -> DrugClipCommandResult:
    try:
        proc = subprocess.run(
            command, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        return DrugClipCommandResult(command, proc.returncode, proc.stdout or "", proc.stderr or "")
    except FileNotFoundError as exc:
        return DrugClipCommandResult(command, 127, "", str(exc))
    except subprocess.TimeoutExpired as exc:
        return DrugClipCommandResult(command, 124, exc.stdout or "", exc.stderr or f"Timed out after {timeout}s")
