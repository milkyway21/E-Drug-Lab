# Linux

```bash
cd /data/ye/e-drug-lab/Scientist_In_E-Drug-Lab
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
export MASLD_COMPETITION_EVAL_MODE=true
masld-agent offline-demo --fixture tests/fixtures/hsd17b13 --output runs
pytest -q
```

Optional Hermes vendor checkout (read-only reference, not required for offline demo):

```bash
git clone --depth 1 https://github.com/NousResearch/hermes-agent.git vendor/hermes-agent
```
