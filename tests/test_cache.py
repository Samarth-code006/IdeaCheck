from app import db
from app.providers.cache import cache_key, get, put


def test_cached_provider_result_prevents_second_call(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "cache.sqlite3")
    db.init_db()
    calls = {"n":0}
    def provider_call():
        calls["n"] += 1
        return {"answer":"stable"}
    key = cache_key(provider="fake", model="v1", prompt_id="extract", prompt_version="1",
                    system="system", user="same input", schema={"type":"object"})
    result = get(key)
    if result is None:
        result = provider_call()
        put(key, result)
    assert get(key) == result
    assert calls["n"] == 1
    changed = cache_key(provider="fake", model="v1", prompt_id="extract", prompt_version="2",
                        system="system", user="same input", schema={"type":"object"})
    assert changed != key
