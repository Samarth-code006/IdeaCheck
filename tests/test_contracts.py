import pytest
from pydantic import ValidationError
from app.contracts import ProposalProfile, evidence_is_substring


def sample_profile():
    return {
        "title": "Sample", "summary": "A small sample proposal.", "problem": "Teams lack comparison.",
        "target_users": ["students"], "features": [
            {"id": f"F{i}", "name": f"Feature {i}", "description": "A described user-facing feature."}
            for i in range(1, 4)
        ], "tech_stack": ["Python"], "domain_tags": ["developer tools", "novelty"], "novelty_claims": []
    }


def test_profile_validates_and_exports_schema():
    profile = ProposalProfile.model_validate(sample_profile())
    assert profile.features[0].id == "F1"
    assert "properties" in ProposalProfile.model_json_schema()


def test_profile_rejects_duplicate_ids_and_unknown_fields():
    data = sample_profile()
    data["features"][1]["id"] = "F1"
    with pytest.raises(ValidationError):
        ProposalProfile.model_validate(data)
    data = sample_profile()
    data["unexpected"] = True
    with pytest.raises(ValidationError):
        ProposalProfile.model_validate(data)


def test_evidence_guard_normalizes_whitespace_and_case():
    assert evidence_is_substring("A   Tiny Claim", "Text: a tiny\nclaim here")
    assert not evidence_is_substring("A changed claim", "Text: a tiny claim here")
