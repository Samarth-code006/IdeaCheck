from app import db
from app.main import app, get_report, jobs, run_artifact_job, run_url_job


def test_artifact_review_job_saves_a_local_project_review(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "blindspot.sqlite3")
    db.init_db()
    jobs["blindspot-job"] = {"events": [], "done": False, "report_id": None, "error": None}
    text = "# Project spec\nStudents need a way to compare local transit options. The app uses an external API and stores user preferences."
    run_artifact_job("blindspot-job", text)
    job = jobs["blindspot-job"]
    assert job["done"] is True
    assert job["report_id"]
    report = get_report(job["report_id"])
    assert report["mode"] == "probe"
    assert report["title"] == "IdeaCheck project review"
    assert [event["data"]["stage"] for event in job["events"] if event["event"] == "stage"] == [
        "understanding", "probing", "prioritizing"
    ]
    assert job["events"][-1]["event"] == "result"


def test_user_api_only_exposes_project_review_not_repository_comparison():
    paths = {route.path for route in app.routes}
    assert "/api/analyze/artifact" in paths
    assert "/api/analyze/repo" not in paths
    assert "/api/analyze/proposal" not in paths
    assert "/api/corpus/ingest" not in paths


def test_url_review_fetches_page_and_saves_source_reference(monkeypatch, tmp_path):
    from app import main
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "blindspot-url.sqlite3")
    db.init_db()
    page_text = "# Campus service\nStudents need reliable meal planning. The service predicts demand from historical meal records and attendance, recommends food preparation, and tracks leftovers for the mess manager."
    monkeypatch.setattr(main, "fetch_reviewable_page", lambda url: {
        "url": "https://example.org/project", "title": "Campus service", "content_type": "text/html", "text": page_text
    })
    jobs["url-job"] = {"events": [], "done": False, "report_id": None, "error": None, "result": None}
    run_url_job("url-job", "https://example.org/project")
    job = jobs["url-job"]
    assert job["done"] is True
    assert job["report_id"]
    report = get_report(job["report_id"])
    assert report["source"]["url"] == "https://example.org/project"
    assert report["source"]["title"] == "Campus service"
    assert any("linked page" in note for note in report["project_model"]["context_assumed"])
