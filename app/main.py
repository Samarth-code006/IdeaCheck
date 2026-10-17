"""FastAPI service and static UI; demo requests never call external providers."""
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from app.config import ROOT
from app.db import connect, init_db
from app.probe import review_artifact
from app.url_fetch import URLReviewError, fetch_reviewable_page
from app.ai_review import local_ai_status, run_local_ai_review

jobs: dict[str, dict] = {}
executor = ThreadPoolExecutor(max_workers=2)


class ArtifactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=40, max_length=20_000)
    use_ai: bool = False


class URLReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    url: str = Field(min_length=10, max_length=2_000)
    use_ai: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="IdeaCheck", version="0.2.0", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def home():
    return FileResponse(ROOT / "web" / "index.html")


@app.get("/api/health")
def health():
    return {"status":"ok","product":"IdeaCheck","analysis":"local deterministic rules","external_ai":False,"public_url_review":True}


@app.get("/api/ai/status")
def ai_status():
    return local_ai_status()


@app.post("/api/analyze/artifact")
def analyze_artifact(request: ArtifactRequest):
    job_id=str(uuid.uuid4())
    jobs[job_id]={"events":[],"done":False,"report_id":None,"error":None,"result":None}
    executor.submit(run_artifact_job,job_id,request.text,request.use_ai)
    return {"job_id":job_id}


@app.post("/api/analyze/url")
def analyze_url(request: URLReviewRequest):
    job_id=str(uuid.uuid4())
    jobs[job_id]={"events":[],"done":False,"report_id":None,"error":None,"result":None}
    executor.submit(run_url_job,job_id,request.url,request.use_ai)
    return {"job_id":job_id}


def _add_ai_review(report: dict, text: str, use_ai: bool):
    if not use_ai:
        report["ai_review"] = {"status": "not_requested"}
        return
    try:
        report["ai_review"] = run_local_ai_review(text)
        report["provider_info"]["ai_review"] = "local Ollama model"
        report["warnings"] = ["The baseline review uses deterministic rules. AI suggestions come from a local language model and may be wrong; verify them against the project context."]
    except Exception as exc:
        # Preserve the deterministic review if the local model is unavailable or fails.
        report["ai_review"] = {"status": "unavailable", "message": str(exc)[:300]}
        report["warnings"].append("The optional local AI review could not run; the deterministic review is still available.")


def run_artifact_job(job_id: str, text: str, use_ai: bool = False):
    try:
        stages=[("understanding",0.2,"Identifying the artifact type, goal, and stated scope."),
                ("probing",0.55,"Checking for unstated assumptions, constraints, and failure paths."),
                ("prioritizing",0.85,"Grounding and ranking the most actionable findings.")]
        for name,progress,detail in stages:
            jobs[job_id]["events"].append({"event":"stage","data":{"stage":name,"status":"done","detail":detail,"progress":progress,"elapsed_ms":0}})
        report=review_artifact(text)
        if use_ai:
            jobs[job_id]["events"].append({"event":"stage","data":{"stage":"ai_review","status":"running","detail":"Asking the optional local model for additional review points.","progress":0.92,"elapsed_ms":0}})
        _add_ai_review(report,text,use_ai)
        if use_ai:
            jobs[job_id]["events"].append({"event":"stage","data":{"stage":"ai_review","status":"done","detail":"Local AI review finished.","progress":0.97,"elapsed_ms":0}})
        with connect() as db:
            db.execute("INSERT INTO reports(report_id,created_at,input_text,report_json,parent_report_id) VALUES(?,?,?,?,NULL)",
                       (report["report_id"],report["created_at"],text,json.dumps(report)))
        jobs[job_id]["report_id"]=report["report_id"]
        jobs[job_id]["events"].append({"event":"result","data":{"report_id":report["report_id"]}})
    except Exception as exc:
        jobs[job_id]["error"]=str(exc)
        jobs[job_id]["events"].append({"event":"stage","data":{"stage":"error","status":"error","detail":str(exc),"progress":1,"elapsed_ms":0}})
    finally:
        jobs[job_id]["done"]=True


def run_url_job(job_id: str, url: str, use_ai: bool = False):
    try:
        jobs[job_id]["events"].append({"event":"stage","data":{"stage":"fetching","status":"running","detail":"Fetching readable text. A sleeping website can take a little while to wake up.","progress":0.1,"elapsed_ms":0}})
        page=fetch_reviewable_page(url)
        jobs[job_id]["events"].append({"event":"stage","data":{"stage":"fetching","status":"done","detail":"Page text fetched.","progress":0.25,"elapsed_ms":0}})
        jobs[job_id]["events"].append({"event":"stage","data":{"stage":"understanding","status":"done","detail":"Identifying the project goal and scope from the page.","progress":0.4,"elapsed_ms":0}})
        report=review_artifact(page["text"])
        if use_ai:
            jobs[job_id]["events"].append({"event":"stage","data":{"stage":"ai_review","status":"running","detail":"Asking the optional local model for additional review points.","progress":0.92,"elapsed_ms":0}})
        _add_ai_review(report,page["text"],use_ai)
        if use_ai:
            jobs[job_id]["events"].append({"event":"stage","data":{"stage":"ai_review","status":"done","detail":"Local AI review finished.","progress":0.97,"elapsed_ms":0}})
        report["source"]={"type":"public_url","url":page["url"],"title":page["title"],"content_type":page["content_type"],"detail":page.get("source_detail","public webpage")}
        report["project_model"]["context_assumed"].append("Only readable text from the linked page was fetched; its JavaScript, authenticated views, source code, and linked pages were not executed or inspected.")
        jobs[job_id]["events"].append({"event":"stage","data":{"stage":"probing","status":"done","detail":"Checking the extracted page text for omissions and risks.","progress":0.7,"elapsed_ms":0}})
        jobs[job_id]["events"].append({"event":"stage","data":{"stage":"prioritizing","status":"done","detail":"Ranking findings and preparing the review.","progress":0.9,"elapsed_ms":0}})
        with connect() as db:
            db.execute("INSERT INTO reports(report_id,created_at,input_text,report_json,parent_report_id) VALUES(?,?,?,?,NULL)",
                       (report["report_id"],report["created_at"],page["text"],json.dumps(report)))
        jobs[job_id]["report_id"]=report["report_id"]
        jobs[job_id]["events"].append({"event":"result","data":{"report_id":report["report_id"]}})
    except Exception as exc:
        detail=str(exc) if isinstance(exc,URLReviewError) else "The page could not be reviewed. Check that it is public and try again."
        jobs[job_id]["error"]=detail
        jobs[job_id]["events"].append({"event":"stage","data":{"stage":"error","status":"error","detail":detail,"progress":1,"elapsed_ms":0}})
    finally:
        jobs[job_id]["done"]=True


@app.get("/api/jobs/{job_id}/events")
def job_events(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, detail={"error":{"code":"JOB_NOT_FOUND","message":"Analysis job was not found.","hint":"Start a new analysis."}})
    def stream():
        cursor, last_heartbeat = 0, time.monotonic()
        while True:
            snapshot = jobs[job_id]["events"]
            while cursor < len(snapshot):
                item = snapshot[cursor]
                cursor += 1
                yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"
            if jobs[job_id]["done"] and cursor >= len(jobs[job_id]["events"]):
                break
            if time.monotonic() - last_heartbeat >= 15:
                yield ": heartbeat\n\n"
                last_heartbeat = time.monotonic()
            time.sleep(0.2)
    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, detail={"error":{"code":"JOB_NOT_FOUND","message":"Analysis job was not found.","hint":"Start a new analysis."}})
    job=jobs[job_id]
    return {"done":job["done"],"report_id":job["report_id"],"error":job["error"],"events":job["events"],"result":job.get("result")}


@app.get("/api/report/{report_id}")
def get_report(report_id: str):
    with connect() as db:
        row = db.execute("SELECT report_json FROM reports WHERE report_id=?",(report_id,)).fetchone()
    if not row:
        raise HTTPException(404, detail={"error":{"code":"REPORT_NOT_FOUND","message":"Report not found.","hint":"Run an analysis first."}})
    return json.loads(row[0])


@app.get("/api/report/{report_id}/export.md")
def export_markdown(report_id: str):
    report = get_report(report_id)
    if report.get("mode")=="probe":
        lines=["# IdeaCheck project review","",report["summary"],"","## Project model",f"- Type: {report['project_model']['artifact_type']}",f"- Domain: {report['project_model']['domain']}",f"- Maturity: {report['project_model']['maturity']}","","Risk score is a heuristic: impact × likelihood (each 1–5); it is not a failure probability.","","## Findings"]
        if report.get("source"):
            lines[3:3]=[f"Source: [{report['source']['title']}]({report['source']['url']})",""]
        for item in report["findings"]:
            evidence=item["evidence"]
            lines += [f"### {item['id']} · {item['tier']} · {item['title']}","",item["description"],"",f"Evidence ({evidence['type']}, {evidence['location']}): {evidence['citation']}","",f"Recommendation: {item['recommendation']['action']}",f"First step: {item['recommendation']['first_step']}",f"Verification: {item['recommendation']['verification']}",""]
        ai_review=report.get("ai_review",{})
        if ai_review.get("status")=="complete":
            lines += ["## Optional local AI suggestions","",ai_review.get("summary","")]
            for item in ai_review.get("findings",[]):
                lines += [f"### {item['title']}","",item["concern"],"",f"Evidence: {item['evidence_quote']}" if item.get("grounded") else "Evidence: AI inference; verify against the project.",f"Possible next step: {item['next_step']}",""]
        lines += ["## Questions to answer",*[f"- {question}" for question in report["questions"]]]
        return Response("\n".join(lines),media_type="text/markdown",headers={"Content-Disposition":f"attachment; filename=ideacheck-{report_id}.md"})
    lines = [f"# {report['proposal_profile']['title']}","",f"Novelty score: {report['novelty_report']['novelty_score']} / 100 (low confidence)","","> Advisory, evidence-based, idea-level similarity. This is not a judgment about any team.","","## Similar projects"]
    for result in report["comparisons"]:
        lines += [f"- [{result['title']}]({result['url']}) — {result['overall_overlap']} overlap ({result['label']})"]
    lines += ["","## Recommendations"]
    for rec in report["novelty_report"]["recommendations"]:
        lines.append(f"{rec['rank']}. {rec['change']} (gap {rec['grounded_in_gap']}, effort {rec['effort']})")
    return Response("\n".join(lines),media_type="text/markdown",headers={"Content-Disposition":f"attachment; filename=novelty-{report_id}.md"})


@app.get("/api/report/{report_id}/export.json")
def export_json(report_id: str):
    report=get_report(report_id)
    return Response(json.dumps(report,ensure_ascii=False,indent=2),media_type="application/json",
                    headers={"Content-Disposition":f"attachment; filename=review-{report_id}.json"})


@app.get("/api/map")
def similarity_map():
    return {"points":[],"note":"Similarity map is deferred; pairwise comparison is available in the feature matrix."}


@app.delete("/api/report/{report_id}")
def delete_report(report_id: str):
    with connect() as db:
        rows=db.execute("WITH RECURSIVE family(id) AS (SELECT report_id FROM reports WHERE report_id=? UNION ALL SELECT reports.report_id FROM reports JOIN family ON reports.parent_report_id=family.id) SELECT id FROM family",(report_id,)).fetchall()
        for row in rows:
            db.execute("DELETE FROM reports WHERE report_id=?",(row[0],))
    return {"deleted":bool(rows),"reports_removed":len(rows)}


app.mount("/static", StaticFiles(directory=ROOT/"web"), name="static")
