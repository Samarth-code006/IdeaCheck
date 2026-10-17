"""Evidence-grounded, offline first-pass review of project artifacts."""
from __future__ import annotations

import re
import csv
import io
import uuid
from datetime import datetime, timezone


def _has(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(term in lowered for term in terms)


def _section_for(lines: list[str], index: int) -> str:
    for line in reversed(lines[:index + 1]):
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if heading:
            return heading.group(1)[:100]
    return "Artifact-wide review"


def _quote(lines: list[str], terms: tuple[str, ...]) -> tuple[str, str] | None:
    for index, line in enumerate(lines):
        if _has(line, terms) and line.strip():
            snippet = line.strip()
            if len(snippet) > 220:
                snippet = snippet[:217].rsplit(" ", 1)[0] + "…"
            return snippet, _section_for(lines, index)
    return None


def _kind(text: str, lines: list[str]) -> tuple[str, str]:
    nonempty = [line for line in lines if line.strip()]
    try:
        widths = [len(row) for row in csv.reader(nonempty) if len(row) > 1]
        modal_width = max(set(widths), key=widths.count) if widths else 0
        consistent_rows = widths.count(modal_width) if modal_width else 0
        csvish = modal_width >= 2 and consistent_rows >= 3 and consistent_rows / max(1, len(nonempty)) >= 0.7
    except csv.Error:
        csvish = False
    if csvish:
        return "dataset", "data"
    if _has(text, ("workflow", "pipeline", "runbook", "process step", "handoff")):
        return "workflow or pipeline", "operations"
    if _has(text, ("readme", "requirements", "api", "database", "server", "software", "application", "code", "repository")):
        return "software project artifact", "software"
    if _has(text, ("proposal", "project", "prototype", "product", "build", "users", "students", "customer")):
        return "project proposal or plan", "product"
    return "project artifact", "general"


def _profile_csv(text: str) -> dict | None:
    try:
        reader=csv.DictReader(io.StringIO(text))
        columns=reader.fieldnames or []
        rows=list(reader)
    except csv.Error:
        return None
    if len(columns)<2 or not rows:
        return None
    missing={column:sum(not (row.get(column) or "").strip() for row in rows) for column in columns}
    duplicates=len(rows)-len({tuple((row.get(column) or "").strip() for column in columns) for row in rows})
    numeric=[]
    for column in columns:
        values=[(row.get(column) or "").strip() for row in rows]
        present=[value for value in values if value]
        if len(present)>=2:
            try:
                [float(value) for value in present]
                numeric.append(column)
            except ValueError:
                pass
    return {"rows":len(rows),"columns":columns[:30],"column_count":len(columns),
            "missing_values":{key:value for key,value in missing.items() if value},
            "exact_duplicate_rows":duplicates,"numeric_columns":numeric}


def _score_finding(finding: dict) -> dict:
    scores = finding["scores"]
    scores["risk_score"] = scores["impact"] * scores["likelihood"]
    # Keep the legacy field during the transition; it now follows the disclosed
    # impact × likelihood formula and is not a probability of failure.
    scores["priority"] = scores["risk_score"]
    risk_score = scores["risk_score"]
    finding["tier"] = "CRITICAL" if risk_score >= 20 else "HIGH" if risk_score >= 12 else "MEDIUM" if risk_score >= 6 else "LOW"
    return finding


def review_artifact(text: str) -> dict:
    """Return concise, grounded findings; this mode never sends text to an LLM."""
    lines = text.splitlines()
    artifact_type, domain = _kind(text, lines)
    dataset_profile=_profile_csv(text) if artifact_type=="dataset" else None
    lower = text.casefold()
    headings = [m.group(1).strip() for line in lines if (m := re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line))]
    first_sentence = next((part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if len(part.split()) >= 5), "")
    goal = first_sentence[:400] or "The artifact does not state a clear goal in its opening text."
    audience_match = _quote(lines, ("users", "students", "customers", "developers", "teams", "staff", "patients", "teachers"))
    audience = audience_match[0] if audience_match else "Not clearly stated in the supplied text."
    maturity = "near launch" if _has(lower, ("launch", "deploy", "production", "release")) else "in progress" if _has(lower, ("implemented", "built", "in progress", "current status")) else "draft" if len(text.split()) > 150 else "idea or early draft"
    findings: list[dict] = []

    def add(*, fid: str, category: str, lens: str, title: str, description: str,
            evidence_terms: tuple[str, ...], absence: str, impact: int, likelihood: int,
            detectability: int, effort: int, confidence: str, failure_scenario: str,
            action: str, first_step: str, verification: str, tradeoff: str,
            questions: list[str], assumption: str):
        found = _quote(lines, evidence_terms) if evidence_terms else None
        evidence = {
            # A matching source line is exact context; otherwise this is explicitly
            # a gap in the supplied documentation, not proof about implementation.
            "type": "DIRECT" if found else "DOCUMENTATION_GAP",
            "citation": found[0] if found else absence,
            "location": found[1] if found else "Not stated in supplied artifact",
        }
        finding = {"id": fid, "category": category, "lens": lens, "title": title,
            "description": description, "evidence": evidence,
            "scores": {"impact": impact, "likelihood": likelihood, "detectability": detectability, "effort": effort},
            "confidence": confidence, "failure_scenario": failure_scenario,
            "recommendation": {"action": action, "first_step": first_step, "verification": verification, "tradeoff": tradeoff},
            "questions": questions, "related_ids": [], "assumption": assumption}
        finding["finding_type"] = "potential omission or unresolved decision"
        findings.append(_score_finding(finding))

    project_like = domain in {"software", "product", "operations"}
    if project_like and not _has(lower, ("success metric", "success criteria", "measure of success", "target metric", "baseline", "kpi", "acceptance criteria")):
        add(fid="P-001", category="assumption", lens="goals and success", title="Success is not defined in a way you can measure",
            description="The artifact describes work or an intended outcome, but does not name a baseline and target that would show whether it helped.",
            evidence_terms=("goal", "aim", "objective", "helps", "improve", "reduce", "increase") if project_like else (),
            absence="No baseline, target, or measurable success criterion is stated in the artifact.", impact=4, likelihood=4, detectability=3, effort=2,
            confidence="medium", failure_scenario="The team can ship the described work yet disagree about whether it solved the original problem.",
            action="Choose one outcome metric, its baseline, and a target before implementation.",
            first_step="Write one sentence in the spec: ‘We will consider this useful if [metric] changes from [baseline] to [target] for [user group].’",
            verification="A reviewer can identify the metric, baseline, target, and measurement window without interpretation.",
            tradeoff="Measuring an outcome takes user access and may narrow the project scope.",
            questions=["Which user outcome matters most, and what baseline and target would count as a meaningful change?"],
            assumption="The proposed deliverables will produce a useful outcome, even though the artifact does not say how that outcome will be measured.")

    if project_like and _has(lower, ("user", "customer", "student", "developer", "team", "staff", "patient", "teacher")) and not _has(lower, ("interview", "usability test", "user test", "test with", "test the prototype with", "pilot", "survey", "feedback", "validated with", "tested with")):
        add(fid="P-002", category="assumption", lens="stakeholders and users", title="The user need appears assumed, not validated",
            description="A user group is named, but the artifact does not describe evidence from those users or a plan to test the need with them.",
            evidence_terms=("users", "students", "customers", "developers", "teams", "staff", "patients", "teachers"),
            absence="No interview, pilot, usability test, survey, or user feedback is described.", impact=4, likelihood=3, detectability=3, effort=2,
            confidence="medium", failure_scenario="The team builds around a plausible problem that target users do not experience as described.",
            action="Validate the highest-risk user need with a small number of target users.",
            first_step="Ask three intended users to walk through their current workaround and what makes it difficult.",
            verification="Record the recurring pain points and update the feature list where user evidence disagrees with the spec.",
            tradeoff="Early conversations may change scope and take time away from implementation.",
            questions=["Who can show the team their current workflow, and what would prove the problem is frequent or costly enough to solve?"],
            assumption="The named audience recognizes the problem and would use the proposed solution.")

    technical = domain in {"software", "operations"} or _has(lower, ("api", "github", "database", "server", "network", "upload", "integration", "pipeline"))
    if technical and not _has(lower, ("retry", "fallback", "timeout", "failure", "error handling", "offline", "recovery", "rollback", "degraded")):
        add(fid="P-003", category="constraint", lens="technical and architectural", title="The failure path for dependencies is unclear",
            description="The artifact mentions a technical system or dependency, but does not explain what it does when a service is slow, unavailable, or returns bad data.",
            evidence_terms=("api", "github", "database", "server", "network", "pipeline", "integration", "service"),
            absence="No retry, timeout, fallback, recovery, or degraded-mode behavior is specified.", impact=4, likelihood=3, detectability=4, effort=3,
            confidence="medium", failure_scenario="A network or provider failure leaves the user waiting, loses work, or produces a misleading result.",
            action="Define timeouts and a user-visible fallback for each external dependency.",
            first_step="List the external services and describe the expected behavior for timeout, rate limit, and invalid response.",
            verification="Simulate one timeout and one rate-limit response; confirm the workflow recovers and explains what happened.",
            tradeoff="Retries and fallback paths add code and can make stale results more likely.",
            questions=["Which dependency can block the main user flow, and what should the user be able to do while it is unavailable?"],
            assumption="External services and network access will be available when the core workflow needs them.")

    data_sensitive = _has(lower, ("email", "personal data", "location", "health data", "account", "identity", "user data", "uploaded file", "proposal text", "preferences", "attendance", "attendance record", "meal attendance", "student attendance"))
    if data_sensitive and not _has(lower, ("retention", "delete", "consent", "privacy", "encryption", "access control", "permission", "data handling")):
        add(fid="P-004", category="constraint", lens="data and privacy", title="Data handling is not explained",
            description="The artifact refers to user, personal, or dataset content but does not say who can access it, how long it is kept, or how it can be removed.",
            evidence_terms=("personal data", "user data", "proposal text", "dataset", "email", "location", "uploaded file", "attendance", "attendance record", "meal attendance", "student attendance"),
            absence="No retention, access, deletion, consent, or privacy handling is stated for the mentioned data.", impact=5, likelihood=3, detectability=4, effort=3,
            confidence="medium", failure_scenario="The project retains or exposes information longer or more broadly than users expect.",
            action="Add a short data-flow and retention section covering collection, access, storage, and deletion.",
            first_step="Trace one user record from entry through storage, processing, logs, exports, and deletion.",
            verification="A reviewer can explain where the data goes, who can access it, and how a user requests deletion.",
            tradeoff="Minimizing retention and access may limit debugging and analytics.",
            questions=["What is the most sensitive field collected, who needs it, and when should it be deleted?"],
            assumption="Handling of the named data is acceptable to users and the project team.")

    validation_terms=("test", "tested", "testing", "validate", "evaluation", "benchmark", "acceptance", "pilot", "measure")
    if technical and not _has(lower, validation_terms):
        add(fid="P-005", category="risk", lens="validation and testing", title="There is no stated plan to check whether the system works",
            description="The artifact does not describe test cases, acceptance criteria, or an evaluation approach for the main workflow.",
            evidence_terms=(), absence="No testing, validation, benchmark, or acceptance criteria are mentioned.", impact=4, likelihood=3, detectability=4, effort=2,
            confidence="medium", failure_scenario="A demo can appear successful while edge cases or the core user outcome remain unverified.",
            action="Define a small acceptance checklist for the primary workflow and its main failure case.",
            first_step="Write three example inputs and expected outcomes, including one invalid or unavailable dependency case.",
            verification="Run the checklist before the demo and record pass/fail results.",
            tradeoff="Testing takes time from feature work but reduces last-minute uncertainty.",
            questions=["What is the smallest test that would convince a skeptical user the main workflow is useful and reliable?"],
            assumption="A successful implementation or demo is enough evidence that the solution works.")

    if project_like and not _has(lower, ("deadline", "timeline", "milestone", "owner", "responsible", "schedule", "due date", "launch date")):
        add(fid="P-006", category="constraint", lens="resources and timeline", title="Ownership and timing are left open",
            description="The artifact does not assign a responsible person or a time boundary to the work, so scope and handoffs may remain ambiguous.",
            evidence_terms=(), absence="No owner, milestone, deadline, or launch date is stated.", impact=3, likelihood=3, detectability=2, effort=1,
            confidence="medium", failure_scenario="Work is deferred between teammates or the core workflow is unfinished at the intended event.",
            action="Name an owner and a deadline for the smallest end-to-end deliverable.",
            first_step="Add one milestone with a named owner and a date, then list what is explicitly out of scope.",
            verification="Every critical deliverable has one owner and a due date.",
            tradeoff="Specific commitments reduce flexibility if assumptions change.",
            questions=["What must be demoable by the deadline, and who owns each dependency on that path?"],
            assumption="The proposed scope fits the available people and time.")

    if dataset_profile and not _has(lower, ("data dictionary", "column definitions", "units", "schema documentation", "field descriptions")):
        add(fid="P-007", category="constraint", lens="data quality and provenance", title="Column meanings and units are undocumented",
            description=f"The pasted table has {dataset_profile['column_count']} columns, but no data dictionary or units are described. Column names alone may not define what values mean.",
            evidence_terms=(), absence="No column definitions, units, or data dictionary are included with the pasted table.",
            impact=3, likelihood=3, detectability=3, effort=2, confidence="medium",
            failure_scenario="Two readers interpret the same field or measurement differently and draw incompatible conclusions.",
            action="Add a short definition, type, unit, and provenance note for each column.",
            first_step="Document the source, grain, timezone, and units for the fields used in the project's key decision.",
            verification="A second person can explain what one row represents and interpret each key field without asking the author.",
            tradeoff="Documentation adds a small maintenance task whenever the schema changes.",
            questions=["What does one row represent, where did each field come from, and which fields have units or timezone assumptions?"],
            assumption="The supplied column names are sufficient for downstream users to interpret the data consistently.")

    predictive = _has(lower, ("predict", "prediction", "forecast", "forecasting", "machine learning", "ml model"))
    if predictive and not _has(lower, ("mae", "rmse", "mape", "mean absolute error", "holdout", "backtest", "time-based split", "forecast baseline", "baseline model", "evaluation metric")):
        add(fid="P-008", category="evaluation", lens="data and machine learning", title="Forecast quality has no stated baseline or evaluation method",
            description="The plan includes prediction or forecasting, but does not name a metric, evaluation window, or simple baseline for judging whether the predictions are useful.",
            evidence_terms=("predict", "prediction", "forecast", "forecasting", "machine learning", "ml model"),
            absence="No forecasting metric, time-based evaluation window, or baseline model is specified in the supplied plan.",
            impact=5, likelihood=4, detectability=3, effort=2, confidence="medium",
            failure_scenario="A forecast can look plausible in a demo while performing no better than a simple historical average, and future data may accidentally influence evaluation.",
            action="Choose an error metric and compare against a simple baseline on a time-ordered holdout period.",
            first_step="Define the forecast horizon and compare a rolling historical average with the proposed model on the same past dates.",
            verification="Report the chosen metric for both approaches on a time-based holdout that was not used to fit the model.",
            tradeoff="A defensible evaluation takes more setup and may reveal that a simple baseline is already sufficient.",
            questions=["What prediction error is acceptable for the manager, over what forecast horizon, and what baseline must the model beat?"],
            assumption="The predictions will be accurate enough to improve decisions without a stated comparison.")

    if predictive and _has(lower, ("historical data", "attendance", "dataset", "consumption data", "weather data")) and not _has(lower, ("missing values", "data quality", "minimum history", "data coverage", "sufficient history", "incomplete data", "imputation")):
        add(fid="P-009", category="constraint", lens="data availability and quality", title="Training data coverage and missing-data handling are unclear",
            description="The plan depends on historical or contextual data, but does not explain how much history is available or what happens when records are incomplete.",
            evidence_terms=("historical data", "attendance", "dataset", "consumption data", "weather data"),
            absence="The supplied plan does not specify minimum data coverage or how incomplete records will be handled.",
            impact=4, likelihood=4, detectability=3, effort=2, confidence="medium",
            failure_scenario="The model may be trained on too little or biased history, or fail on a day when attendance or weather data is unavailable.",
            action="Audit historical coverage by meal and define a fallback for missing inputs before selecting a forecasting model.",
            first_step="Count usable observations per meal across weekdays, holidays, and seasonal periods, then record missingness by field.",
            verification="A data summary shows the available history and the model or fallback behavior for each required input when absent.",
            tradeoff="A narrower feature set can reduce model complexity but may also limit the signals available to explain demand changes.",
            questions=["How many complete historical observations exist for each meal, and what should the system do when an input is missing?"],
            assumption="The project has enough representative history and complete contextual data to produce useful predictions." )

    if _has(lower, ("food waste", "food wastage", "leftovers")) and not _has(lower, ("weigh leftovers", "weigh the leftovers", "measure food waste", "measured food waste", "leftover weight", "waste in kg", "kg of waste", "prepared quantity", "quantity consumed", "weighed waste")):
        add(fid="P-010", category="evaluation", lens="outcome measurement", title="The food-waste outcome has no stated measurement method",
            description="The plan aims to reduce food waste or track leftovers, but does not say how waste will be measured consistently.",
            evidence_terms=("food waste", "food wastage", "leftovers"),
            absence="No measurement procedure or unit for food waste is specified in the supplied plan.",
            impact=4, likelihood=4, detectability=3, effort=2, confidence="medium",
            failure_scenario="A dashboard may show changing leftover estimates that reflect inconsistent recording rather than a real reduction in waste.",
            action="Define a repeatable waste measurement and record it alongside prepared and consumed quantities.",
            first_step="Specify who measures leftovers, when they do it, which unit they use, and how each meal or dish is recorded.",
            verification="Two staff members following the procedure produce comparable waste measurements for the same meal.",
            tradeoff="Consistent measurement adds a small task at meal close and may require a scale or a practical estimation protocol.",
            questions=["Will waste be weighed or estimated, at what level (meal or dish), and who records the result?"],
            assumption="The project can demonstrate reduced waste using the information its current workflow collects.")

    if not findings:
        findings.append(_score_finding({"id":"P-000","category":"question","lens":"scope and requirements","title":"The supplied artifact is too thin for a useful review",
            "description":"I could not find enough project-specific detail to make grounded findings. Add the goal, intended users, key workflow, and constraints, then review it again.",
            "evidence":{"type":"DIRECT","citation":text[:180],"location":"Supplied artifact"},
            "scores":{"impact":2,"likelihood":2,"detectability":2,"effort":1},"confidence":"high",
            "failure_scenario":"Any specific review would rely on guesses about the project.",
            "recommendation":{"action":"Add project context before relying on the review.","first_step":"Describe the problem, user, proposed workflow, and what success looks like.","verification":"The artifact names the audience, goal, and one testable outcome.","tradeoff":"More context takes time to write but makes the review more specific."},
            "questions":["Who is this for, what should change for them, and how will you know?"],"related_ids":[],"assumption":"There is not enough context to infer project assumptions reliably."}))

    findings.sort(key=lambda item:(-item["scores"]["risk_score"], item["scores"]["effort"], item["id"]))
    findings=findings[:8]
    questions=[]
    for finding in findings:
        for question in finding["questions"]:
            if question not in questions:
                questions.append(question)
    skipped=[]
    if domain != "data":
        skipped.append({"lens":"Dataset profiling","reason":"The pasted content was not clearly structured as a tabular dataset."})
    if not _has(lower, ("health", "finance", "children", "employment", "education", "location", "personal data")):
        skipped.append({"lens":"Domain-specific regulation","reason":"No clearly regulated or sensitive domain was identified from the supplied text; applicability was not assessed."})
    if not _has(lower, ("deployment", "production", "monitoring", "support", "maintenance", "operations")):
        skipped.append({"lens":"Production operations","reason":"The artifact does not provide enough operational context to assess monitoring, support, or deployment readiness."})

    assumptions=[{"assumption":item["assumption"],"status":"implicit","evidence":item["evidence"],"risk_if_false":item["failure_scenario"],"how_to_test":item["recommendation"]["verification"],"expiry_trigger":"Revisit when scope, users, dependencies, or launch conditions change."} for item in findings if item["id"]!="P-000"]
    goal_present=bool(first_sentence)
    summary=f"This looks like a {artifact_type} at the {maturity} stage. I found {len(findings)} review point(s); the highest-risk point by a simple impact × likelihood score is {findings[0]['title'].lower()}. This is a rules-based first pass over the supplied text; confirm each point before acting."
    model={"artifact_type":artifact_type,"domain":domain,"maturity":maturity,"goal":{"value":goal,"status":"stated" if goal_present else "missing"},
        "scope":{"value":"; ".join(headings[:8]) if headings else "No explicit section outline found.","status":"stated" if headings else "missing"},
        "stakeholders":{"value":audience,"status":"implied" if audience_match else "missing"},
        "timeline":{"value":"Mentioned in the artifact." if _has(lower,("deadline","timeline","milestone","schedule","due date")) else "Not stated.","status":"stated" if _has(lower,("deadline","timeline","milestone","schedule","due date")) else "missing"},
        "success_criteria":{"value":"Mentioned in the artifact." if _has(lower,("success metric","success criteria","baseline","target metric","kpi","acceptance criteria")) else "Not stated.","status":"stated" if _has(lower,("success metric","success criteria","baseline","target metric","kpi","acceptance criteria")) else "missing"},
        "components":headings[:12],"context_assumed":["Only the pasted text was reviewed; linked files, code, and external systems were not inspected."]}
    contradictions=[]
    if _has(lower,("works offline","offline mode","offline-first")) and _has(lower,("requires internet","internet connection required","must be online")):
        contradictions.append("The artifact claims offline use and also says an internet connection is required; clarify which core workflows work offline.")
    return {"report_id":str(uuid.uuid4()),"created_at":datetime.now(timezone.utc).isoformat(),"mode":"probe","title":"IdeaCheck project review","summary":summary,"context_assumed":model["context_assumed"],"project_model":model,
        "findings":findings,"questions":questions[:10],"assumptions":assumptions,"contradictions":contradictions,"skipped_lenses":skipped,
        "dataset_profile":dataset_profile,"provider_info":{"review":"local rule-based review"},"warnings":["This first-pass review uses local rules, not an LLM. It can miss nuance and should be checked against the full project context."]}
