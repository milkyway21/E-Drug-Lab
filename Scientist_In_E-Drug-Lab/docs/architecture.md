# Architecture

Supervisor CLI orchestrates deterministic tools; Hermes Plugin/Skill/MCP are thin wrappers.

```text
masld-agent CLI ──► supervisor
                      ├─ competition parser
                      ├─ target generator (curated panel)
                      ├─ evidence (Europe PMC / UniProt / Open Targets)
                      ├─ novelty critic
                      ├─ PDB / pocket
                      ├─ PubChem / ChEMBL
                      ├─ RDKit / optional Vina
                      ├─ deterministic scoring
                      ├─ evidence critic
                      └─ proposal / method / JSON report
```

Priorities: reproducibility > evidence truthfulness > scientific caution > feature count.
