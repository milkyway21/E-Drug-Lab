# Vendor note

`vendor/hermes-agent` is **not** shipped in this repository (large third-party tree).

Install locally after clone:

```bash
cd Scientist_In_E-Drug-Lab
mkdir -p vendor
git clone --depth 1 https://github.com/NousResearch/hermes-agent.git vendor/hermes-agent
source .venv/bin/activate
pip install -e ./vendor/hermes-agent
```

Do not edit Hermes core. This project extends Hermes via Plugin / Skill / MCP.
