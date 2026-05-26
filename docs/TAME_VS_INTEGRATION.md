# TAME-VS integration

This project vendors the upstream TAME-VS repository at:

```text
tools/Target-driven-ML-enabled-VS
```

Upstream source:

```text
https://github.com/bymgood/Target-driven-ML-enabled-VS
```

## Execution boundary

All TAME-VS execution is intentionally routed through Windows WSL Docker:

```powershell
C:\Windows\System32\wsl.exe docker ...
```

If a specific WSL distribution is configured:

```powershell
C:\Windows\System32\wsl.exe -d eDrugUbuntu docker ...
```

The backend does not run TAME-VS directly on Windows Python. It only prepares inputs, calls WSL Docker, then imports outputs.

## Docker image

The Dockerfile is:

```text
tools/Target-driven-ML-enabled-VS/Dockerfile.edrug
```

It uses `ghcr.io/mamba-org/micromamba:1.5.10`, installs Python 3.7/RDKit/scientific dependencies from conda-forge, then installs `chembl_webresource_client` with pip. This avoids Docker Hub access for the base image and avoids RDKit pip wheel compatibility issues.

Build through the API:

```http
POST /api/v1/tame-vs/build-image
```

Or manually:

```powershell
C:\Windows\System32\wsl.exe docker build -t edrug-lab/tame-vs:latest -f /mnt/e/e-drug-lab/tools/Target-driven-ML-enabled-VS/Dockerfile.edrug /mnt/e/e-drug-lab/tools/Target-driven-ML-enabled-VS
```

With the local `eDrugUbuntu` distribution:

```powershell
C:\Windows\System32\wsl.exe -d eDrugUbuntu docker build -t edrug-lab/tame-vs:latest -f /mnt/e/e-drug-lab/tools/Target-driven-ML-enabled-VS/Dockerfile.edrug /mnt/e/e-drug-lab/tools/Target-driven-ML-enabled-VS
```

## API endpoints

```http
GET /api/v1/tame-vs/status
```

Checks WSL, Docker, image configuration, repo path, and Dockerfile path.

```http
POST /api/v1/tame-vs/smoke-test
```

Creates a tiny two-molecule CSV, runs TAME-VS `Library_preparation.py` inside Docker, and if the output CSV exists, converts it into SDF and imports it into the molecule database.

```http
POST /api/v1/tame-vs/prepare-library
```

Runs TAME-VS fingerprint preparation for a user-provided CSV.

Example body:

```json
{
  "input_csv": "E:/e-drug-lab/outputs/tame-vs/my_library.csv",
  "output_name": "my_library_morgan_1024_FP",
  "smiles_col": 2,
  "compound_id_col": 1,
  "auto_ingest": true
}
```

```http
POST /api/v1/tame-vs/ingest-results
```

Converts a TAME-VS result CSV containing `smiles`, `SMILES`, `Molecule (RDKit Mol)`, or `canonical_smiles` into SDF, writes it under:

```text
molecules/sdf/tame_vs/
```

Then calls the existing SDF sync pipeline so the molecules appear in the molecule database.

## Current environment note

On this machine, WSL 2.7.3 is installed and an Ubuntu 24.04 WSL2 distribution named `eDrugUbuntu` is imported under:

```text
E:\WSL\eDrugUbuntu
```

Docker Engine 29.5.2 is installed inside that distribution and the local TAME-VS image was built as:

```text
edrug-lab/tame-vs:latest
```

Validated smoke path: `POST /api/v1/tame-vs/smoke-test` runs `Library_preparation.py` in WSL Docker, writes `outputs/tame-vs/tame_vs_smoke_morgan_1024_FP.csv`, converts it to `molecules/sdf/tame_vs/tame_vs_smoke_morgan_1024_FP.sdf`, and syncs the full `molecules/sdf` library.
