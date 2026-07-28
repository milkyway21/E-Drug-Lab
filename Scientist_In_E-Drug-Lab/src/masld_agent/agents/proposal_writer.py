"""Proposal / method writers."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from masld_agent.models import CompetitionProfile, TargetHypothesis


def write_proposal_md(
    path: Path,
    *,
    profile: CompetitionProfile,
    hypotheses: Iterable[TargetHypothesis],
) -> None:
    hyps = list(hypotheses)
    lines = [
        f"# Proposal — {profile.competition_name}",
        "",
        f"> **{profile.competition_scope_warning.strip()}**",
        "",
        f"- Competition URL: {profile.competition_url}",
        f"- Active disease scope: **{profile.disease_active.value}**",
        "- Agent role: target hypothesis & mechanism (compound Top10 library nomination remains external)",
        "",
        "## Executive summary",
        "",
        "This proposal ranks mechanistic small-molecule inhibitor targets relevant to early "
        "hepatocyte lipid overload / lipotoxicity under the MASLD competition framing. "
        "Claims are evidence-gated; unverified literature is excluded from final tables.",
        "",
        "## Ranked target hypotheses",
        "",
    ]
    for i, h in enumerate(hyps, 1):
        total = h.scores.total
        lines += [
            f"### {i}. {h.gene_symbol} ({h.uniprot_id or 'UniProt n/a'})",
            "",
            f"- Novelty class: `{h.novelty_class.value}`",
            f"- Score total: {total if total is not None else 'n/a'} "
            f"(missing dims: {', '.join(h.scores.missing_dimensions) or 'none'})",
            f"- Scientific significance: {h.scientific_significance or 'see evidence table'}",
            f"- Clinical significance: {h.clinical_significance or 'see evidence table'}",
            f"- Uncertainty: {h.uncertainty}",
            "",
            "Evidence (verified only):",
            "",
        ]
        for e in h.evidence:
            if not e.verified:
                continue
            cite = e.pmid or e.doi or e.url or "source-only"
            lines.append(f"- {e.title or e.supports_claim} [{cite}] ({e.source})")
        if h.structures:
            lines.append("")
            lines.append("Structures:")
            for s in h.structures:
                af = " [AlphaFold prediction]" if s.is_alphafold else ""
                lines.append(
                    f"- {s.pdb_id} reso={s.resolution_A} method={s.method}{af} — {s.selection_reason}"
                )
        if h.pockets:
            lines.append("")
            lines.append("Pockets:")
            for p in h.pockets:
                lines.append(
                    f"- {p.pocket_type}: residues {', '.join(p.key_residues)} ({p.selection_reason})"
                )
        if h.ligands:
            lines.append("")
            lines.append("Reference ligands:")
            for lig in h.ligands:
                lines.append(
                    f"- {lig.name} role=`{lig.role.value}` CID={lig.pubchem_cid} "
                    f"SMILES=`{lig.smiles}`"
                )
        lines.append("")

    lines += [
        "## Validation outline",
        "",
        "For each top target: HepG2-FFA lipid accumulation + parallel viability; "
        "orthogonal mechanism assays; optional organoid/animal follow-up. "
        "Do not claim 'already proven effective' without clinical citations.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_method_md(
    path: Path,
    *,
    profile: CompetitionProfile,
    offline: bool,
) -> None:
    text = f"""# Method — Scientist_In_E-Drug-Lab

## Scope warning

{profile.competition_scope_warning.strip()}

## Pipeline

1. Competition Requirement Parser → structured `CompetitionProfile` (JSON).
2. Target Candidate Generator → curated mechanism seed panel (not LLM-only memory).
3. Evidence Retrieval → Europe PMC / PubMed / UniProt / Open Targets (when online).
4. Novelty Critic → established / emerging / novel_hypothesis.
5. Structure & Pocket → RCSB PDB (+ explicit AlphaFold labeling).
6. Ligand Reference → PubChem / optional ChEMBL with role tags.
7. Molecular Evaluation → RDKit descriptors + PAINS; docking optional (Vina).
8. Deterministic scoring (`config/scoring.yaml`) — missing dims never scored as 1.0.
9. Evidence Critic → opposing risks / uncertainty.
10. Proposal Writer → proposal.md, method.md, machine_readable_report.json.

## Reproducibility

- Offline mode: `masld-agent offline-demo --fixture tests/fixtures/hsd17b13`
- Online mode: `masld-agent run --competition config/competition_life_science.yaml`
- HTTP responses cached under `.cache/http` with SHA256 metadata.
- Hermes competition eval mode disables auto skill mutation / uncontrolled memory.

## Offline flag

offline={offline}
"""
    path.write_text(text, encoding="utf-8")
