from app import db
from app.config import get_config
from app.extraction.profile import extract_proposal


def test_profile_extraction_uses_validated_offline_fallback(monkeypatch,tmp_path):
    from app.providers.factory import get_llm_provider
    monkeypatch.setattr(db,"DB_PATH",tmp_path/"profile.sqlite3")
    db.init_db()
    monkeypatch.setenv("NOVELTY_MODE","local-only")
    get_config.cache_clear()
    get_llm_provider.cache_clear()
    text="A project helps student teams compare ideas against public repositories. It extracts a problem and feature profile. It retrieves similar projects, shows README evidence, finds open gaps, and recommends changes teams can test. Teams edit the proposal and rerun to review the result."
    result=extract_proposal(text)
    assert result.source=="heuristic"
    assert len(result.profile.features)>=3
    get_config.cache_clear()
    get_llm_provider.cache_clear()


def test_local_only_mode_does_not_construct_remote_provider(monkeypatch):
    from app.providers.factory import get_llm_provider
    monkeypatch.setenv("NOVELTY_MODE","local-only")
    monkeypatch.setenv("LLM_PROVIDER","openai_compat")
    monkeypatch.delenv("OLLAMA_MODEL",raising=False)
    get_config.cache_clear()
    get_llm_provider.cache_clear()
    assert get_llm_provider().name=="fake"
    get_config.cache_clear()
    get_llm_provider.cache_clear()
