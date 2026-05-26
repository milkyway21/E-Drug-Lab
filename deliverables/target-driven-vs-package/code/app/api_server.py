from __future__ import annotations

import csv
import os
import pickle
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing_extensions import Literal


WORKSPACE = Path(os.getenv("WORKSPACE_DIR", "/workspace"))
CODE_DIR = WORKSPACE / "code" / "tame-vs"
DATA_DIR = WORKSPACE / "data"
MODELS_DIR = WORKSPACE / "models"
RESULTS_DIR = DATA_DIR / "results"
TIMEOUT_SECONDS = int(os.getenv("TAME_VS_TIMEOUT", "1800"))
PRELOAD_MODELS = os.getenv("TAME_VS_PRELOAD_MODELS", "false").lower() == "true"


app = FastAPI(title="Target-driven ML-enabled VS API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

loaded_models = {}  # type: Dict[str, Any]


class Compound(BaseModel):
    comp_id: str = Field(..., description="Compound identifier")
    smiles: str = Field(..., description="Canonical or input SMILES")


class InferenceRequest(BaseModel):
    task: Literal["prepare_library", "virtual_screening"] = "prepare_library"
    input_csv: Optional[str] = Field(None, description="CSV path inside the container, usually under /workspace/data")
    compounds: Optional[List[Compound]] = Field(None, description="Inline compound list; used when input_csv is omitted")
    smiles_col: int = Field(2, ge=1, description="1-based SMILES column index")
    compound_id_col: int = Field(1, ge=1, description="1-based compound id column index")
    fp_type: Literal["Morgan", "AtomPair", "Topological", "MACCS"] = "Morgan"
    number_of_bits: int = Field(1024, ge=64, le=8192)
    model_path: Optional[str] = Field(None, description="Model .sav path inside /workspace/models or an absolute container path")
    model_type: Optional[Literal["MLP", "RF"]] = None
    output_name: Optional[str] = None
    preview_rows: int = Field(20, ge=0, le=500)


def _gpu_available() -> bool:
    if shutil.which("nvidia-smi") is None:
        return False
    result = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=10)
    return result.returncode == 0


def _safe_path(path_value: str, base: Optional[Path] = None) -> Path:
    path = Path(path_value)
    if not path.is_absolute() and base is not None:
        path = base / path
    path = path.resolve()
    allowed_roots = [DATA_DIR.resolve(), MODELS_DIR.resolve()]
    if not any(path == root or root in path.parents for root in allowed_roots):
        raise HTTPException(status_code=400, detail=f"Path must be under /workspace/data or /workspace/models: {path}")
    return path


def _run(command: List[str], cwd: Path) -> Dict[str, Any]:
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT_SECONDS,
    )
    payload = {
        "command": command,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=payload)
    return payload


def _write_compounds_csv(compounds: List[Compound], request_id: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    input_csv = DATA_DIR / f"{request_id}_library.csv"
    with input_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["comp_id", "smiles"])
        writer.writeheader()
        for compound in compounds:
            writer.writerow(compound.dict())
    return input_csv


def _preview_csv(path: Path, rows: int) -> List[Dict[str, Any]]:
    if rows <= 0 or not path.exists():
        return []
    frame = pd.read_csv(path).head(rows)
    if frame.shape[1] > 24:
        # Keep payload compact for wide fingerprint tables.
        keep_cols = list(frame.columns[:24])
        frame = frame.loc[:, keep_cols]
    return frame.where(pd.notnull(frame), None).to_dict(orient="records")


def _find_model(model_path: Optional[str], model_type: Optional[str]) -> Path:
    if model_path:
        path = _safe_path(model_path, MODELS_DIR)
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Model not found: {path}")
        return path

    candidates = sorted(MODELS_DIR.glob("*.sav"))
    if model_type:
        typed = [path for path in candidates if model_type.lower() in path.name.lower()]
        candidates = typed or candidates
    if not candidates:
        raise HTTPException(status_code=404, detail="No .sav model found under /workspace/models")
    return candidates[0]


@app.on_event("startup")
def startup() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if PRELOAD_MODELS:
        for model_file in sorted(MODELS_DIR.glob("*.sav")):
            with model_file.open("rb") as fh:
                loaded_models[model_file.name] = pickle.load(fh)


@app.get("/health")
def health() -> Dict[str, Any]:
    model_files = [path.name for path in sorted(MODELS_DIR.glob("*.sav"))]
    return {
        "status": "ok",
        "gpu": _gpu_available(),
        "models_loaded": sorted(loaded_models.keys()),
        "models_available": model_files,
        "preload": PRELOAD_MODELS,
    }


@app.post("/inference")
def inference(body: InferenceRequest) -> Dict[str, Any]:
    request_id = uuid.uuid4().hex[:12]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if body.input_csv:
        input_csv = _safe_path(body.input_csv, DATA_DIR)
    elif body.compounds:
        input_csv = _write_compounds_csv(body.compounds, request_id)
    else:
        raise HTTPException(status_code=400, detail="Provide either input_csv or compounds")

    if not input_csv.exists():
        raise HTTPException(status_code=404, detail=f"Input CSV not found: {input_csv}")

    output_prefix = body.output_name or f"{request_id}_{body.task}"
    fingerprint_prefix = RESULTS_DIR / f"{output_prefix}_morgan_{body.number_of_bits}_FP"
    fingerprint_csv = fingerprint_prefix.with_suffix(".csv")

    prep_command = [
        "python",
        str(CODE_DIR / "5_Virtural_screening" / "Library_preparation.py"),
        "-i",
        str(input_csv),
        "-s",
        str(body.smiles_col),
        "-c",
        str(body.compound_id_col),
        "-t",
        body.fp_type,
        "-n",
        str(body.number_of_bits),
        "-f",
        str(fingerprint_prefix),
    ]
    prep_result = _run(prep_command, cwd=RESULTS_DIR)

    response: Dict[str, Any] = {
        "request_id": request_id,
        "task": body.task,
        "input_csv": str(input_csv),
        "fingerprint_csv": str(fingerprint_csv),
        "prepare": prep_result,
        "preview": _preview_csv(fingerprint_csv, body.preview_rows),
    }

    if body.task == "virtual_screening":
        model_path = _find_model(body.model_path, body.model_type)
        inferred_type = body.model_type or ("MLP" if "mlp" in model_path.name.lower() else "RF")
        score_prefix = RESULTS_DIR / f"{output_prefix}_{inferred_type}_scores"
        score_csv = score_prefix.with_suffix(".csv")
        screen_command = [
            "python",
            str(CODE_DIR / "5_Virtural_screening" / "Virtual_screening.py"),
            "-m",
            str(model_path),
            "-t",
            inferred_type,
            "-s",
            str(fingerprint_csv),
            "-f",
            str(score_prefix),
        ]
        screen_result = _run(screen_command, cwd=RESULTS_DIR)
        response.update(
            {
                "model_path": str(model_path),
                "model_type": inferred_type,
                "score_csv": str(score_csv),
                "screening": screen_result,
                "preview": _preview_csv(score_csv, body.preview_rows),
            }
        )

    return response
