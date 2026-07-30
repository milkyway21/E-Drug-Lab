"""Unit tests — models & scoring."""
from masld_agent.models import NoveltyClass
from masld_agent.scoring import classify_novelty, score_target


def test_missing_dims_not_full_score():
    s = score_target(
        dimension_scores={
            "human_genetics_evidence": 1.0,
            "disease_mechanism_relevance": None,
            "hepatocyte_or_liver_specificity": None,
            "druggability": None,
            "structure_availability": None,
            "ligand_precedent": None,
            "safety_rationale": None,
            "novelty": None,
        }
    )
    assert s.total == 1.0  # only one present dim
    assert "novelty" in s.missing_dimensions


def test_novelty_classification():
    assert (
        classify_novelty(
            has_approved_drug=False,
            has_late_clinical=True,
            has_early_clinical_or_strong_preclinical=True,
        )
        == NoveltyClass.ESTABLISHED
    )
    assert (
        classify_novelty(
            has_approved_drug=False,
            has_late_clinical=False,
            has_early_clinical_or_strong_preclinical=True,
        )
        == NoveltyClass.EMERGING
    )
