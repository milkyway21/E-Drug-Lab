# Open-Source Foundations

These target-research skills adapt general workflow patterns from
[`K-Dense-AI/scientific-agent-skills`](https://github.com/K-Dense-AI/scientific-agent-skills),
commit `ad21a3868923628330734375dddbf7b86ea84222` (MIT License, Copyright 2025
K-Dense Inc.). Relevant upstream skills were `literature-review`, `database-lookup`,
`bioservices`, `pathway-enrichment`, and `torchdrug`.

The project-specific adaptation:

- removes unavailable `parallel-cli`, visualization, and package-install requirements
- routes through existing E-Drug-Lab tools and optional academic-search MCP tools
- adds target-direction, pharmacology, contradictory-evidence, and applicability hard gates
- links computational assessment to the existing E2/E2b/E3 structure workflow
- adds explicit artifacts suitable for competition reproducibility

No upstream executable scripts are vendored. Database endpoints and current behavior must be
checked against their official documentation before changing adapters.
