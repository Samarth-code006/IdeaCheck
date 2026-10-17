from app.probe import review_artifact


def test_probe_review_finds_project_specific_missing_controls_and_cites_text():
    text = """# Campus project
Students struggle to track campus shuttle arrivals. Our app calls the public Transit API and stores route preferences for students.
The app sends alerts when the bus is near and shows arrival estimates.
"""
    report = review_artifact(text)
    assert report["mode"] == "probe"
    assert report["project_model"]["artifact_type"] == "software project artifact"
    ids = {finding["id"] for finding in report["findings"]}
    assert {"P-001", "P-002", "P-003", "P-004", "P-005", "P-006"} <= ids
    finding = next(item for item in report["findings"] if item["id"] == "P-003")
    assert finding["evidence"]["type"] == "DIRECT"
    assert finding["evidence"]["citation"]
    assert finding["recommendation"]["verification"]
    assert finding["scores"]["risk_score"] == finding["scores"]["impact"] * finding["scores"]["likelihood"]
    assert finding["scores"]["priority"] == finding["scores"]["risk_score"]


def test_probe_does_not_claim_a_missing_success_metric_when_one_is_stated():
    text = """# Goals
The target metric is to reduce average waiting time by 20% within one month.
We will test the prototype with students and use an offline fallback when the transit service is unavailable.
The team will deliver the first milestone next Friday.
"""
    report = review_artifact(text)
    assert "P-001" not in {finding["id"] for finding in report["findings"]}
    assert "P-002" not in {finding["id"] for finding in report["findings"]}
    assert "P-003" not in {finding["id"] for finding in report["findings"]}


def test_probe_thin_artifact_returns_calibrated_context_gap():
    report = review_artifact("A short note with no further detail.")
    assert len(report["findings"]) == 1
    assert report["findings"][0]["id"] == "P-000"
    assert report["findings"][0]["confidence"] == "high"


def test_probe_profiles_csv_and_flags_unexplained_columns():
    text = """id,wait_seconds,student_email
1,12,a@example.edu
2,,b@example.edu
2,,b@example.edu
"""
    report = review_artifact(text)
    assert report["project_model"]["artifact_type"] == "dataset"
    assert report["dataset_profile"]["rows"] == 3
    assert report["dataset_profile"]["missing_values"]["wait_seconds"] == 2
    assert report["dataset_profile"]["exact_duplicate_rows"] == 1
    assert "P-007" in {finding["id"] for finding in report["findings"]}
    assert "P-004" in {finding["id"] for finding in report["findings"]}


def test_probe_flags_direct_offline_requirement_conflict():
    report = review_artifact("The project works offline. The main workflow requires internet access.")
    assert report["contradictions"]


def test_project_prose_with_commas_is_not_misclassified_as_csv():
    report = review_artifact("""# MessMind
College mess managers need to prepare food without waste. The project predicts demand from historical meal consumption, attendance, weekdays, holidays, and weather.
Managers review predictions and actual leftovers, and students can rate meals.
""")
    assert report["project_model"]["artifact_type"] == "project proposal or plan"
    ids = {finding["id"] for finding in report["findings"]}
    assert {"P-008", "P-009", "P-010", "P-004"} <= ids
    assert report["dataset_profile"] is None


def test_forecast_gap_is_not_reported_when_baseline_and_evaluation_are_stated():
    report = review_artifact("""The project predicts meal demand using historical attendance and consumption data.
We will compare the forecast to a rolling historical-average baseline using MAE on a time-based holdout. Data quality and missing values are checked before training.
""")
    ids = {finding["id"] for finding in report["findings"]}
    assert "P-008" not in ids
    assert "P-009" not in ids


def test_food_waste_measurement_gap_is_documentation_gap_not_claim_of_failure():
    report = review_artifact("The hostel plan aims to reduce food waste and track leftovers for each meal.")
    finding = next(item for item in report["findings"] if item["id"] == "P-010")
    assert finding["evidence"]["type"] == "DIRECT"
    assert "does not say how waste will be measured" in finding["description"]
    assert finding["evidence"]["citation"] == "The hostel plan aims to reduce food waste and track leftovers for each meal."
