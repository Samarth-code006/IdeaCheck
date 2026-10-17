"""Rule-based extractor used offline; clearly marked as heuristic, not an LLM."""
import re
from app.contracts import Feature, ProposalProfile
from app.retrieval.bm25 import tokenize

TECHS = {"python", "fastapi", "sqlite", "react", "typescript", "javascript", "faiss", "pytorch", "postgresql", "mongodb", "docker", "ollama", "sentence-transformers"}


def extract_profile(text: str) -> ProposalProfile:
    cleaned = " ".join(text.split())
    sentences = [part.strip(" -*\t") for part in re.split(r"(?<=[.!?])\s+|\n+", text) if len(part.split()) >= 4]
    raw_title = next((line.strip("# -*") for line in text.splitlines() if line.strip()), "Untitled project")
    title = " ".join(raw_title.split()[:9])[:120]
    feature_sentences = [part.strip(" -*\t,;:") for part in re.split(r"(?<=[.!?])\s+|\n+|,\s+|\band\b", text) if len(part.split()) >= 4]
    if len(feature_sentences) < 3:
        feature_sentences = sentences
    if len(feature_sentences) > 6:
        feature_sentences = [feature_sentences[round(i * (len(feature_sentences)-1) / 5)] for i in range(6)]
    feature_sentences = (feature_sentences + ["The project provides an accessible workflow for its target users."] * 3)[:6]
    features = [Feature(id=f"F{i+1}", name=" ".join(line.split()[:7]).rstrip(".,:")[:60], description=line[:240])
                for i, line in enumerate(feature_sentences[:6])]
    words = set(tokenize(cleaned))
    tech = sorted(words & TECHS)
    problem_sentence = next((s for s in sentences if not re.search(r"\b(build|create|develop|provide|offer)\b", s, re.I)), "Teams need clearer information before choosing a project direction.")
    summary = cleaned[:600] if cleaned else "A project proposal awaiting more detail."
    tags = [tag for tag in ("project discovery", "developer tools", "information retrieval", "decision support") if any(token in words for token in tokenize(tag))]
    tags = (tags + ["project discovery", "decision support"])[:4]
    return ProposalProfile(title=title, summary=summary, problem=problem_sentence[:500],
        target_users=["project teams"], features=features, tech_stack=tech,
        domain_tags=tags, novelty_claims=[])
