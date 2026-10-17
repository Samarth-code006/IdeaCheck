"""Feature alignment and optional batched LLM verification with quote validation."""
import json
from app.config import get_config
from app.contracts import evidence_is_substring
from app.prompts.verify_features import SYSTEM,VERSION
from app.providers.cache import cached_generate_json
from app.providers.factory import get_llm_provider

SCHEMA={
    "type":"object",
    "properties":{"pairs":{
        "type":"array",
        "items":{
            "type":"object",
            "properties":{
                "pair_id":{"type":"string"},
                "verdict":{"type":"string","enum":["same","partial","different"]},
                "explanation":{"type":"string"},
                "evidence_quote":{"type":["string","null"]},
            },
            "required":["pair_id","verdict","explanation","evidence_quote"],
            "additionalProperties":False,
        },
    }},
    "required":["pairs"],
    "additionalProperties":False,
}


def verify_candidates(pairs:list[dict],provider=None)->dict[str,dict]:
    """Return validated verdicts; unsupported verdicts are downgraded to different."""
    provider=provider or get_llm_provider()
    if provider.name=="fake" or not pairs:
        return {}
    limit=get_config()["compare"]["feature_pairs_per_feature"]
    payload={"pairs":pairs[:limit*5]}
    try:
        response=cached_generate_json(provider,system=SYSTEM,user=json.dumps(payload,ensure_ascii=False),schema=SCHEMA,
           prompt_id="features.verify",prompt_version=VERSION,temperature=0)
    except Exception:
        # Keep feature matching usable when an optional provider times out or is
        # misconfigured; the caller transparently falls back to heuristic pairs.
        return {}
    if not response:
        return {}
    verified={}
    for item in response.get("pairs",[]):
        source=next((pair for pair in pairs if pair["pair_id"]==item.get("pair_id")),None)
        if source is None: continue
        verdict=item.get("verdict","different")
        quote=item.get("evidence_quote")
        if verdict in {"same","partial"} and (not quote or len(quote)>240 or not evidence_is_substring(quote,source["repo_chunk_text"])):
            verdict="different"
            quote=None
        verified[source["pair_id"]]={"verdict":verdict,"explanation":item.get("explanation",""),"evidence_quote":quote}
    return verified
