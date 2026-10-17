"""Compact BM25 implementation for the offline corpus; heuristic IR, not ML."""
import math
import re
from collections import Counter

TOKEN = re.compile(r"[a-z0-9+#.-]+")
STOP = {"the", "and", "for", "with", "from", "that", "this", "are", "was", "into", "using", "use", "your", "you", "their", "they", "project", "app"}


def tokenize(text: str) -> list[str]:
    return [word for word in TOKEN.findall(text.casefold()) if len(word) > 1 and word not in STOP]


def rank(query: str, documents: list[dict], k: int = 10, k1: float = 1.5, b: float = 0.75) -> list[dict]:
    if not documents:
        return []
    terms = tokenize(query)
    token_docs = [tokenize(doc.get("text", "")) for doc in documents]
    avgdl = sum(map(len, token_docs)) / len(token_docs) or 1.0
    df = Counter(term for tokens in token_docs for term in set(tokens))
    scored = []
    for doc, tokens in zip(documents, token_docs):
        tf, length = Counter(tokens), len(tokens)
        score = 0.0
        for term in terms:
            freq = tf[term]
            if freq:
                idf = math.log(1 + (len(documents) - df[term] + 0.5) / (df[term] + 0.5))
                score += idf * freq * (k1 + 1) / (freq + k1 * (1 - b + b * length / avgdl))
        scored.append((score, doc))
    return [dict(doc, score=score) for score, doc in sorted(scored, key=lambda item: (-item[0], item[1].get("repo_id", "")))[:k]]
