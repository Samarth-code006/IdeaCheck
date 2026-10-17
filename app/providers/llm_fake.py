"""Deterministic offline provider used by demo and tests; no network calls."""
import hashlib
import json


class FakeLLM:
    name = "fake"
    model = "deterministic-fixture-v1"

    def generate_json(self, *, system: str, user: str, schema: dict,
                      prompt_id: str, prompt_version: str, temperature: float = 0.0,
                      max_tokens: int = 1500) -> dict:
        # Prompt-keyed deterministic response prevents demo results drifting.
        digest = hashlib.sha256((prompt_id + user).encode()).hexdigest()[:12]
        if prompt_id in {"proposal.extract", "repo.extract"}:
            from app.extraction.heuristic import extract_profile
            return extract_profile(user).model_dump(mode="json")
        if prompt_id == "features.verify":
            try:
                pairs=json.loads(user).get("pairs",[])
            except (json.JSONDecodeError,AttributeError):
                pairs=[]
            return {"pairs":[{"pair_id":item.get("pair_id",""),"verdict":"different","explanation":"Offline fixture uses no semantic verifier.","evidence_quote":None} for item in pairs]}
        return {"fixture": prompt_id, "input_hash": digest}

    def generate_text(self, *, system: str, user: str, prompt_id: str,
                      prompt_version: str, temperature: float = 0.0,
                      max_tokens: int = 800) -> str:
        return f"Offline fixture for {prompt_id}: {hashlib.sha256(user.encode()).hexdigest()[:12]}"
