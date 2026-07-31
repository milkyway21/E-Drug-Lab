# Architecture

Supervisor CLI orchestrates deterministic tools; Hermes Plugin/Skill/MCP are thin wrappers.
The E0-E6 evidence envelope preserves the existing H0-H10 compute-stage contract.

```text
masld-agent CLI ──► E0 scope and library identity
                   ├─ E1 target biology (UniProt / Open Targets / Reactome / literature)
                   ├─ E2 RCSB structure search and ranking
                   ├─ E3 pocket qualification and conditional docking decision
                   ├─ H0-H10 existing generation / docking / ADMET / MD funnel
                   ├─ E4 exact compound identity and activity enrichment
                   ├─ E5 observed / predicted / unknown toxicity triage
                   └─ E6 deterministic ranking / mechanism / validation / provenance
```

Priorities: reproducibility > evidence truthfulness > scientific caution > feature count.
