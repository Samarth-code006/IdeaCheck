"""Transparent heuristic similarity scoring; no classifier is trained here."""
from app.retrieval.bm25 import tokenize
from app.config import get_config


def similarity(a: str, b: str) -> float:
    left, right = set(tokenize(a)), set(tokenize(b))
    return len(left & right) / len(left | right) if left and right else 0.0


def label(score: float) -> str:
    thresholds=get_config()["compare"]["label_thresholds"]
    if score >= thresholds["near_duplicate"]: return "near_duplicate"
    if score >= thresholds["strong_overlap"]: return "strong_overlap"
    if score >= thresholds["partial_overlap"]: return "partial_overlap"
    if score >= thresholds["related"]: return "related"
    return "distinct"


def overall(problem: float, feature: float, tech: float) -> float:
    # Shared technology is a weak signal, so the template keeps its weight low.
    weights=get_config()["compare"]["weights"]
    return max(0.0, min(100.0, 100 * (weights["problem"] * problem + weights["feature"] * feature + weights["tech"] * tech)))
