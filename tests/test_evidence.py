from app.explain.evidence import extract_snippet


def test_evidence_requires_literal_substring():
    chunk = {"chunk_id": "x#1", "text": "The project supports offline check in for clinics.", "source_url": "https://example.test"}
    assert extract_snippet("offline check in", chunk)["snippet"]
    assert extract_snippet("AI scheduling", chunk) == {"status": "no evidence"}
