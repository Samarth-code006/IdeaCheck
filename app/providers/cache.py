"""Stable content-addressed cache for provider calls."""
import hashlib
import json
import hashlib
from datetime import datetime, timezone
from app.db import connect
from app.config import get_config


def cache_key(*, provider: str, model: str, prompt_id: str, prompt_version: str,
              system: str, user: str, schema: dict | None = None,
              temperature: float = 0.0) -> str:
    payload = {"provider": provider, "model": model, "prompt_id": prompt_id,
               "prompt_version": prompt_version, "system": system, "user": user,
               "schema_hash": hashlib.sha256(json.dumps(schema or {}, sort_keys=True).encode()).hexdigest(),
               "temperature": temperature}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def get(key: str) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT response_json FROM llm_cache WHERE cache_key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def put(key: str, result: dict, latency_ms: int = 0) -> None:
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO llm_cache(cache_key,response_json,created_at,latency_ms) VALUES(?,?,?,?)",
                   (key, json.dumps(result, sort_keys=True), datetime.now(timezone.utc).isoformat(), latency_ms))


def cached_generate_json(provider, *, system: str, user: str, schema: dict,
                         prompt_id: str, prompt_version: str, temperature: float = 0.0):
    """Read-through cache honoring demo read-only mode; returns None on an uncached demo call."""
    mode=get_config()["cache"]["mode"]
    key=cache_key(provider=provider.name,model=provider.model,prompt_id=prompt_id,
                  prompt_version=prompt_version,system=system,user=user,schema=schema,
                  temperature=temperature)
    cached=get(key) if mode!="off" else None
    if cached is not None:
        return cached
    if mode=="read_only":
        return None
    import time
    started=time.monotonic()
    result=provider.generate_json(system=system,user=user,schema=schema,prompt_id=prompt_id,
                                  prompt_version=prompt_version,temperature=temperature)
    if mode=="read_write":
        put(key,result,int((time.monotonic()-started)*1000))
    return result


def cached_embed(provider,texts:list[str],*,kind:str="passage"):
    """Cache stable local-model vectors by model and text hash; TF-IDF is corpus-fit and uncached."""
    mode=get_config()["cache"]["mode"]
    if provider.name=="tfidf" or mode=="off":
        return provider.embed(texts,kind=kind)
    hashes=[hashlib.sha256(text.encode()).hexdigest() for text in texts]
    output=[None]*len(texts)
    with connect() as db:
        for index,digest in enumerate(hashes):
            row=db.execute("SELECT vector_json FROM embedding_cache WHERE model=? AND text_hash=?",(provider.model,digest)).fetchone()
            if row: output[index]=json.loads(row[0])
    missing=[i for i,value in enumerate(output) if value is None]
    if missing:
        vectors=provider.embed([texts[i] for i in missing],kind=kind)
        for index,vector in zip(missing,vectors):
            output[index]=vector
        if mode=="read_write":
            with connect() as db:
                db.executemany("INSERT OR REPLACE INTO embedding_cache(model,text_hash,vector_json) VALUES(?,?,?)",
                    [(provider.model,hashes[i],json.dumps(output[i])) for i in missing])
    return output
