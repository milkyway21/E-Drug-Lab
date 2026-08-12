# Architecture

Supervisor CLI orchestrates deterministic tools; Hermes Plugin/Skill/MCP are thin wrappers.
The E0-E6 evidence envelope preserves the existing H0-H10 compute-stage contract.

```text
masld-agent CLI ──► E0 scope and library identity
                   ├─ E1 target identity and seed evidence
                   ├─ E1a biomedical literature / genetics / tissue / pathway evidence
                   ├─ E1b target pharmacology / ligands / direction / safety
                   ├─ E2 RCSB structure search and ranking
                   ├─ E2a computational-pharmacology route and applicability assessment
                   ├─ E2b native receptor/ligand download, cleaning, and coordinate validation
                   ├─ E3 pocket qualification and conditional docking decision
                   ├─ H0-H10 existing generation / docking / ADMET / MD funnel
                   ├─ E4 exact compound identity and activity enrichment
                   ├─ E5 observed / predicted / unknown toxicity triage
                   └─ E6 deterministic ranking / mechanism / validation / provenance
```

Priorities: reproducibility > evidence truthfulness > scientific caution > feature count.

## Skill routing

The project skill library is grouped into eight flowchart-aligned master skills:
`drug-discovery-orchestrator`, `target-discovery`, `dd-generation`, `virtual-docking`,
`featurehit-finding`, `admet`, `molecular-dynamics`, and `all-analysis`. Each master routes
to the existing named child skills. Flat child-name paths remain compatibility symlinks and
are not published a second time to Hermes, preventing duplicate skill selection.
