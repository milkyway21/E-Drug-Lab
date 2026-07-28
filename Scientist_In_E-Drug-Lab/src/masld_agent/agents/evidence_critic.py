"""Evidence critic — opposing risks and uncertainty."""
from __future__ import annotations

from masld_agent.models import EvidenceLevel, EvidenceRecord, SafetyConcern, TargetHypothesis


def critique_hypothesis(hyp: TargetHypothesis) -> TargetHypothesis:
    opposing: list[EvidenceRecord] = list(hyp.opposing_evidence)
    safety: list[SafetyConcern] = list(hyp.safety_concerns)

    # Generic mechanism-level cautions (documented as heuristic critic, not fake papers).
    safety.append(
        SafetyConcern(
            source="evidence_critic",
            evidence_level=EvidenceLevel.D,
            confidence=0.5,
            warnings=[],
            provenance={"rule": "lipotoxicity_tradeoff"},
            concern=(
                "Inhibiting lipid synthesis / storage pathways may increase free fatty acid "
                "load or shift toxicity to other tissues; monitor plasma lipids and mitochondrial stress."
            ),
            severity="moderate",
            mitigation="Pair lipid readout with viability, ALT/AST, and mitochondrial assays.",
        )
    )
    if hyp.gene_symbol.upper() == "KHK":
        opposing.append(
            EvidenceRecord(
                source="evidence_critic",
                evidence_level=EvidenceLevel.C,
                confidence=0.6,
                warnings=[],
                provenance={"note": "heuristic"},
                title="Fructose-pathway inhibition may have systemic metabolic effects",
                supports_claim="possible_systemic_tradeoffs",
                verified=False,
                abstract_excerpt=(
                    "Critic note: strong target biology does not imply absence of on-target "
                    "systemic effects; clinical programs should be cited when claiming novelty."
                ),
            )
        )
        hyp.uncertainty = (
            (hyp.uncertainty + " ").strip()
            + "KHK has substantial clinical investment — treat novelty claims conservatively."
        )

    if hyp.novelty_class.value == "established_target":
        hyp.warnings.append("Novelty critic: established_target — avoid 'new target' language.")

    hyp.opposing_evidence = opposing
    hyp.safety_concerns = safety
    if not hyp.uncertainty:
        hyp.uncertainty = (
            "Causal direction (lipid drop vs cytotoxicity) must be experimentally separated; "
            "computational scores are not efficacy proof."
        )
    return hyp
