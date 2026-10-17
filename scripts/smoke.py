"""Offline demo smoke check; emits only values measured by this run."""
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app.db as db
from app.db import init_db, get_repos
from app.ingestion.ingest import seed_demo_corpus
from app.pipeline import analyze
from app.main import samples


def main():
    with tempfile.TemporaryDirectory(prefix="novelty-smoke-") as temp:
        db.DB_PATH = Path(temp) / "smoke.sqlite3"
        init_db()
        seed_demo_corpus()
        proposals = samples()["samples"]
        print(f"Corpus: {len(get_repos())} repository records")
        for sample in proposals:
            report = analyze(sample["text"])
            top = report["comparisons"][0]["repo_id"] if report["comparisons"] else "none"
            print(f"PASS {sample['name']}: novelty={report['novelty_report']['novelty_score']}; top={top}; recommendations={len(report['novelty_report']['recommendations'])}")


if __name__ == "__main__":
    main()
