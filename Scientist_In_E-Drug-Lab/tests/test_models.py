from masld_agent.models import CompetitionProfile, DiseaseScope, EvidenceLevel


def test_competition_profile_requires_scope_warning():
    p = CompetitionProfile(
        source="test",
        evidence_level=EvidenceLevel.A,
        confidence=0.9,
        competition_url="https://example.com",
        competition_scope_warning="competition_scope_warning: confirm MASLD vs HCC with organizers.",
        disease_active=DiseaseScope.MASLD,
    )
    assert "competition_scope_warning" in p.competition_scope_warning
    dumped = p.model_dump()
    assert dumped["disease_active"] == DiseaseScope.MASLD
