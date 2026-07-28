"""Deterministic / curated target candidate generation (not LLM memory-only)."""
from __future__ import annotations

from typing import Optional

from masld_agent.models import DiseaseScope, EvidenceLevel, TargetCandidate

# Curated seed panel for MASLD early lipid overload / lipotoxicity mechanisms.
# Used only as a starting set for tooling; scores still require evidence retrieval.
MASLD_SEED_PANEL: list[dict] = [
    {
        "gene_symbol": "HSD17B13",
        "uniprot_id": "Q7Z5P4",
        "mechanisms": ["lipid_droplet", "retinol_metabolism", "lipotoxicity"],
        "rationale": "LD-associated enzyme; human genetics links to NAFLD/MASLD severity.",
    },
    {
        "gene_symbol": "KHK",
        "uniprot_id": "P50053",
        "mechanisms": ["fructose_metabolism", "de_novo_lipogenesis"],
        "rationale": "Ketohexokinase (KHK-C) drives fructose-dependent DNL; strong clinical precedent.",
    },
    {
        "gene_symbol": "FASN",
        "uniprot_id": "P49327",
        "mechanisms": ["de_novo_lipogenesis"],
        "rationale": "Canonical DNL enzyme in hepatocytes.",
    },
    {
        "gene_symbol": "DGAT2",
        "uniprot_id": "Q96PD7",
        "mechanisms": ["lipid_droplet", "triglyceride_synthesis"],
        "rationale": "Final step TG synthesis; LD formation.",
    },
    {
        "gene_symbol": "CD36",
        "uniprot_id": "P16671",
        "mechanisms": ["fatty_acid_uptake"],
        "rationale": "Fatty acid uptake transporter in hepatocytes.",
    },
    {
        "gene_symbol": "SCD",
        "uniprot_id": "O00767",
        "mechanisms": ["de_novo_lipogenesis", "lipotoxicity"],
        "rationale": "Stearoyl-CoA desaturase in lipogenic program.",
    },
    {
        "gene_symbol": "PNPLA3",
        "uniprot_id": "Q9NST1",
        "mechanisms": ["lipid_droplet", "lipotoxicity"],
        "rationale": "Strong human genetics in fatty liver disease (I148M).",
    },
    {
        "gene_symbol": "ACLY",
        "uniprot_id": "P53396",
        "mechanisms": ["de_novo_lipogenesis"],
        "rationale": "Cytosolic acetyl-CoA generation for DNL.",
    },
    {
        "gene_symbol": "GPAM",
        "uniprot_id": "Q9HCL2",
        "mechanisms": ["triglyceride_synthesis", "mitochondrial_stress"],
        "rationale": "Glycerol-3-phosphate acyltransferase in TG pathway.",
    },
    {
        "gene_symbol": "MLXIPL",
        "uniprot_id": "Q9NP71",
        "mechanisms": ["de_novo_lipogenesis", "fructose_metabolism"],
        "rationale": "ChREBP transcription factor controlling lipogenic genes.",
    },
]


def generate_candidates(
    disease: DiseaseScope = DiseaseScope.MASLD,
    *,
    top_n: int = 10,
    extra: Optional[list[TargetCandidate]] = None,
) -> list[TargetCandidate]:
    if disease == DiseaseScope.HCC:
        warnings = [
            "HCC mode selected intentionally; do not mix into MASLD submission without confirmation."
        ]
    else:
        warnings = []

    out: list[TargetCandidate] = []
    for row in MASLD_SEED_PANEL[:top_n]:
        out.append(
            TargetCandidate(
                source="curated_seed_panel",
                evidence_level=EvidenceLevel.D,
                confidence=0.4,
                warnings=list(warnings),
                provenance={"panel": "MASLD_SEED_PANEL", "disease": disease.value},
                gene_symbol=row["gene_symbol"],
                uniprot_id=row.get("uniprot_id"),
                rationale=row["rationale"],
                mechanisms=list(row.get("mechanisms") or []),
            )
        )
    if extra:
        out.extend(extra)
    return out
