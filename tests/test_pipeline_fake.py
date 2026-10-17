from app import db
from app.ingestion.ingest import seed_demo_corpus
from app.pipeline import analyze
from app.contracts import evidence_is_substring


def test_offline_pipeline_is_repeatable_and_returns_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.sqlite3")
    db.init_db()
    seed_demo_corpus()
    text = ("Novelty Coach helps hackathon participants and mentors understand how a new project idea overlaps with public repositories. "
            "Teams describe the problem, users, features, and technology. The system extracts a structured idea profile, "
            "searches related repositories, compares feature coverage, and shows exact README evidence. It identifies white space "
            "and recommends specific ways to differentiate. Teams can edit the proposal and run a what-if comparison.")
    first, second = analyze(text), analyze(text)
    assert first["novelty_report"]["novelty_score"] == second["novelty_report"]["novelty_score"]
    assert len(first["novelty_report"]["recommendations"]) == 5
    assert first["comparisons"]
    for comparison in first["comparisons"]:
        for match in comparison["feature_matches"]:
            evidence = match["evidence"]
            assert evidence == {"status": "no evidence"} or evidence_is_substring(evidence["snippet"], next(r["readme"] for r in db.get_repos() if r["repo_id"] == comparison["repo_id"]))
    assert all(rec["grounded_in_gap"] in {g["gap_id"] for g in first["novelty_report"]["white_space"]}
               for rec in first["novelty_report"]["recommendations"])
