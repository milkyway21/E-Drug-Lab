# Target-driven ML-enabled VS Delivery Package

This package deploys the TAME-VS molecular virtual-screening workflow as a local HTTP API on Windows through WSL2 and Docker.

Upstream project:

```text
https://github.com/bymgood/Target-driven-ML-enabled-VS
```

## What This Project Contains

TAME-VS is not a video-monitoring or PyTorch model project. It is a target-driven molecular virtual screening workflow.

Model count:

| Model | Type | Where It Is Created | Weight File |
| --- | --- | --- | --- |
| Random Forest | scikit-learn `RandomForestClassifier` | `code/tame-vs/4_ML_modeling_training/ML_model_training.py` | `<target>_random_forest.sav` |
| MLP | scikit-learn `MLPClassifier` | `code/tame-vs/4_ML_modeling_training/ML_model_training.py` | `<target>_MLP.sav` |

There are no pretrained `.sav`, `.pt`, `.pth`, or `.h5` weights in the upstream repository. The `.sav` files are generated after training on active/inactive fingerprint CSV files. Put trained `.sav` files in `models/` before running `virtual_screening`.

Dependency declaration:

```text
code/tame-vs/requirements.txt
```

Main workflow entry points:

| Step | File |
| --- | --- |
| Target expansion | `code/tame-vs/1_Target_expansion/Target_expansion.py` |
| Compound retrieval | `code/tame-vs/2_Compound_retrieving/Compound_retrieving.py` |
| Vectorization | `code/tame-vs/3_Vectorization/Vectorization.py` |
| Model training | `code/tame-vs/4_ML_modeling_training/ML_model_training.py` |
| Library fingerprint preparation | `code/tame-vs/5_Virtural_screening/Library_preparation.py` |
| Virtual screening | `code/tame-vs/5_Virtural_screening/Virtual_screening.py` |
| Post VS analysis | `code/tame-vs/6_Post_VS_analysis/Post_VS_analysis.py` |
| Result merge/ranking | `code/tame-vs/7_Data_processing/Data_processing.py` |
| HTTP wrapper | `code/app/api_server.py` |

## Hardware Requirements

Minimum for TAME-VS API:

| Resource | Minimum | Recommended |
| --- | ---: | ---: |
| Windows | Windows 10 22H2 / Windows 11 | Windows 11 |
| CPU | 4 cores | 8+ cores |
| RAM | 8 GB | 16 GB+ |
| Disk | 8 GB free | 20 GB+ free |
| GPU | Not required for TAME-VS | NVIDIA GPU for other model packages |
| VRAM | 0 GB for TAME-VS | 8 GB+ for GPU model packages |

The `docker-compose.yml` keeps NVIDIA runtime settings because this package is intended as a template for GPU model delivery. TAME-VS itself runs on CPU, and `setup.bat` will automatically retry with `docker-compose.cpu.yml` if NVIDIA runtime startup fails.

## Three-Step Startup

1. Extract the package.
2. Double-click `setup.bat`.
3. Wait until it prints `Deployment complete`.

After startup, the API listens at:

```text
http://localhost:8000
```

## API

### GET `/health`

Response:

```json
{
  "status": "ok",
  "gpu": false,
  "models_loaded": [],
  "models_available": [],
  "preload": false
}
```

`models_available` lists `.sav` files mounted in `models/`. Set `TAME_VS_PRELOAD_MODELS=true` in `docker-compose.yml` only when you want to load all `.sav` files during startup.

### POST `/inference`

Task `prepare_library` calculates molecular fingerprints.

Request:

```json
{
  "task": "prepare_library",
  "compounds": [
    {"comp_id": "aspirin", "smiles": "CC(=O)OC1=CC=CC=C1C(=O)O"},
    {"comp_id": "caffeine", "smiles": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C"}
  ],
  "fp_type": "Morgan",
  "number_of_bits": 1024,
  "output_name": "demo"
}
```

Response includes:

```json
{
  "task": "prepare_library",
  "fingerprint_csv": "/workspace/data/results/demo_morgan_1024_FP.csv",
  "preview": []
}
```

Task `virtual_screening` calculates fingerprints and scores them with a `.sav` model in `models/`.

Request:

```json
{
  "task": "virtual_screening",
  "input_csv": "/workspace/data/my_library.csv",
  "model_path": "/workspace/models/CDK1_random_forest.sav",
  "model_type": "RF",
  "output_name": "cdk1_screen"
}
```

Response includes:

```json
{
  "score_csv": "/workspace/data/results/cdk1_screen_RF_scores.csv",
  "model_type": "RF",
  "preview": []
}
```

## VRAM Reference

| Component | VRAM |
| --- | ---: |
| TAME-VS fingerprint preparation | 0 GB |
| TAME-VS RF screening | 0 GB |
| TAME-VS MLP screening | 0 GB |
| Generic GPU model packages using this template | model dependent |

## Common Commands

Run from this package directory through WSL:

```bash
docker compose logs -f
docker compose restart
docker compose down
docker compose up -d
```

Windows examples:

```powershell
wsl -d Ubuntu-22.04 -- bash -lc "cd /mnt/c/path/to/target-driven-vs-package && docker compose logs -f"
wsl -d Ubuntu-22.04 -- bash -lc "cd /mnt/c/path/to/target-driven-vs-package && docker compose down"
```

## Common Issues

Port 8000 is already occupied:

Edit `docker-compose.yml` and change:

```yaml
ports:
  - "8001:8000"
```

NVIDIA runtime is unavailable:

Install the NVIDIA Windows driver with WSL support and NVIDIA Container Toolkit inside WSL. For CPU-only TAME-VS, remove `runtime: nvidia` and the NVIDIA environment variables from `docker-compose.yml`.

The setup script fallback command is:

```bash
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d
```

No model is available for `virtual_screening`:

Put a trained `.sav` model under `models/`, for example:

```text
models/CDK1_random_forest.sav
models/CDK1_MLP.sav
```

How to update the model:

1. Stop the service with `docker compose down`.
2. Replace files in `models/`.
3. Start the service with `docker compose up -d`.

## Package Build Command

From the parent directory:

```bash
tar -czvf target-driven-vs-package.tar.gz \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.git' \
  --exclude='data' \
  target-driven-vs-package/
```

Windows PowerShell equivalent:

```powershell
Compress-Archive -Path .\target-driven-vs-package -DestinationPath .\target-driven-vs-package.zip -Force
```
