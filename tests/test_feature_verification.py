from types import SimpleNamespace
from app.compare import features


def pair():
    return {"pair_id":"r:F1","proposal_feature":{"id":"F1","name":"Offline mode","description":"Works without a connection."},
            "repo_feature_text":"The tool works offline.","repo_chunk_id":"r#1","repo_chunk_text":"The tool works offline for field teams."}


def test_verifier_keeps_exact_quotes_and_downgrades_fabricated_quotes(monkeypatch):
    monkeypatch.setattr(features,"cached_generate_json",lambda *args,**kwargs:{"pairs":[
        {"pair_id":"r:F1","verdict":"partial","explanation":"Both mention offline use.","evidence_quote":"works offline for field teams"}]})
    result=features.verify_candidates([pair()],SimpleNamespace(name="stub"))
    assert result["r:F1"]["verdict"]=="partial"
    monkeypatch.setattr(features,"cached_generate_json",lambda *args,**kwargs:{"pairs":[
        {"pair_id":"r:F1","verdict":"same","explanation":"Unsupported.","evidence_quote":"runs with no internet ever"}]})
    result=features.verify_candidates([pair()],SimpleNamespace(name="stub"))
    assert result["r:F1"]["verdict"]=="different"
    assert result["r:F1"]["evidence_quote"] is None
