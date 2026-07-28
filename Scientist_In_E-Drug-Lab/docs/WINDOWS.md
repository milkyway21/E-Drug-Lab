# Windows

Recommended: **WSL2** then follow `LINUX.md`.

## PowerShell (native)

```powershell
cd C:\path\to\Scientist_In_E-Drug-Lab
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
$env:MASLD_COMPETITION_EVAL_MODE = "true"
masld-agent offline-demo --fixture tests/fixtures/hsd17b13 --output runs
pytest -q
```

If RDKit wheels fail on native Windows, use WSL2.
