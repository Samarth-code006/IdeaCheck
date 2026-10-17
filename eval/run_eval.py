"""Small transparent smoke evaluation; synthetic labels are not a quality claim."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.compare.scoring import similarity

ROOT = Path(__file__).resolve().parents[1]
PAIRS = [
    ("semantic repository recommendation with README evidence", "find similar repositories with semantic search and explain results", 1),
    ("student course timetable conflict checker", "recipe sharing and meal planning for families", 0),
    ("project idea overlap analysis for hackathons", "project idea overlap analysis for hackathons using public repositories", 1),
    ("offline clinic queue estimates", "weather alerts for coastal fishing communities", 0),
]


def main():
    rows = [(similarity(a,b), label) for a,b,label in PAIRS]
    threshold = 0.15
    tp = sum(score >= threshold and label == 1 for score,label in rows)
    fp = sum(score >= threshold and label == 0 for score,label in rows)
    fn = sum(score < threshold and label == 1 for score,label in rows)
    precision = tp / max(1,tp+fp)
    recall = tp / max(1,tp+fn)
    f1 = 2*precision*recall/max(1e-12,precision+recall)
    content = ["# Evaluation results", "", "This is a tiny synthetic smoke benchmark, not a measured production-quality claim.",
        f"Pairs: {len(rows)} (2 synthetic positive, 2 synthetic negative). Threshold: {threshold:.2f}.", "",
        "| Metric | Result |", "|---|---:|", f"| Precision | {precision:.3f} |", f"| Recall | {recall:.3f} |", f"| F1 | {f1:.3f} |", "",
        "This smoke check measures only the lexical similarity function on these four hand-authored pairs. Neural embeddings, reranking, LLM verification and confidence intervals are not measured here."]
    target = ROOT / "eval" / "results.md"
    target.write_text("\n".join(content)+"\n")
    print("\n".join(content))


if __name__ == "__main__":
    main()
