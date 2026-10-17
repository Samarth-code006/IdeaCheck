"""Evidence selection with substring verification; never fabricate quotations."""
from app.contracts import evidence_is_substring


def extract_snippet(needle: str, chunk: dict, max_chars: int = 240) -> dict:
    text = " ".join(chunk.get("text", "").split())
    target = " ".join(needle.split())
    offset = text.casefold().find(target.casefold()) if target else -1
    if offset < 0:
        return {"status": "no evidence"}
    start = max(0, offset - 45)
    snippet = text[start:start + max_chars]
    if not evidence_is_substring(snippet, text):
        return {"status": "no evidence"}
    return {"chunk_id": chunk.get("chunk_id", "readme#001"), "snippet": snippet,
            "source_url": chunk.get("source_url", "")}
