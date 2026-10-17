"""End-to-end heuristic demo pipeline, with every comparison tied to corpus text."""
from datetime import datetime, timezone
import json
import re
import uuid
from app.compare.scoring import label, overall, similarity
from app.db import connect, get_repos, get_chunks
from app.explain.evidence import extract_snippet
from app.extraction.profile import extract_proposal
from app.retrieval.hybrid import retrieve
from app.config import get_config
from app.contracts import evidence_is_substring
from app.retrieval.bm25 import tokenize
from app.compare.features import verify_candidates
import time


def feature_similarity(a: str, b: str) -> float:
    """Lexical overlap coefficient keeps short feature labels comparable to README sentences."""
    left, right = set(tokenize(a)), set(tokenize(b))
    return len(left & right) / min(len(left), len(right)) if left and right else 0.0

BANNED = re.compile(r"\b(copied|stolen|plagiarized|plagiarism|plagiarised)\b", re.I)


def safe_text(value: str) -> str:
    """Remove accusatory terms from generated or template text as a final guard."""
    return "" if BANNED.search(value) else value


def sanitize_generated(value, key=""):
    if isinstance(value,dict):
        return {name:sanitize_generated(item,name) for name,item in value.items()}
    if isinstance(value,list):
        return [sanitize_generated(item,key) for item in value]
    if isinstance(value,str) and key not in {"input","snippet"}:
        return safe_text(value)
    return value


def analyze(text: str, parent_report_id: str | None = None, on_stage=None, exclude_repo_id: str | None = None, allow_short: bool = False, mode: str = "hybrid") -> dict:
    started = time.monotonic()
    config=get_config()
    def stage(name: str, progress: float, detail: str):
        if on_stage:
            on_stage(name, progress, int((time.monotonic()-started)*1000), detail)
    stage("extracting", 0.05, "Building a structured profile with the offline heuristic.")
    if len(text.split()) < config["analysis"]["min_words"] and not allow_short:
        raise ValueError("Please add more detail (at least 20 words), including who has the problem and what they need.")
    extraction=extract_proposal(text)
    profile = extraction.profile
    stage("extracting", 0.18, "Profile extracted.")
    repos = [repo for repo in get_repos() if repo["repo_id"] != (exclude_repo_id or "").lower()]
    query = " ".join([profile.problem, profile.summary, *(f.name + " " + f.description for f in profile.features)])
    chunks_by_repo={}
    for chunk in get_chunks():
        chunks_by_repo.setdefault(chunk["repo_id"],[]).append(chunk)
    docs=[]
    for repo in repos:
        context=" ".join([repo["title"],repo["description"]," ".join(repo["topics"])])
        chunks=chunks_by_repo.get(repo["repo_id"])
        if chunks:
            docs.extend(dict(repo,chunk_id=chunk["chunk_id"],text=context+" "+chunk["text"]) for chunk in chunks)
        else:
            docs.append(dict(repo,text=context+" "+repo["readme"]))
    stage("retrieving", 0.22, f"Searching {len(repos)} cached public repositories.")
    retrieved,retrieval_trace=retrieve(query,docs,mode=mode,final_k=config["analysis"]["final_k"])
    stage("retrieving", 0.38, f"Retrieved {len(retrieved)} candidates using {mode} mode.")
    by_id = {repo["repo_id"]: repo for repo in repos}
    comparisons, coverage_by_feature = [], {f.id: [] for f in profile.features}
    stage("comparing", 0.42, "Comparing problems, feature terms, and technology overlap.")
    for rank_no, retrieved_row in enumerate(retrieved, start=1):
        repo_id=retrieved_row["repo_id"]
        repo = by_id[repo_id]
        p_sim = similarity(profile.problem, repo["description"] + " " + repo["readme"])
        matches, feature_values, evidence_count = [], [], 0
        candidates=[]
        selected_features=[]
        for feature in profile.features:
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", repo["readme"]) if s.strip()]
            best = max(sentences, key=lambda sentence: feature_similarity(feature.name, sentence), default="")
            raw = feature_similarity(feature.name, best)
            verdict_thresholds=config["compare"]["lexical_feature_verdicts"]
            verdict = "same" if raw >= verdict_thresholds["same_min"] else "partial" if raw >= verdict_thresholds["partial_min"] else "different"
            pair_id=f"{repo_id}:{feature.id}"
            candidates.append({"pair_id":pair_id,"proposal_feature":{"id":feature.id,"name":feature.name,"description":feature.description},
                               "repo_feature_text":best,"repo_chunk_id":repo_id+"#readme","repo_chunk_text":repo["readme"]})
            selected_features.append((feature,best,raw,verdict,pair_id))
        verified=verify_candidates(candidates)
        verification_ran=bool(verified)
        for feature,best,raw,heuristic_verdict,pair_id in selected_features:
            checked=verified.get(pair_id)
            verdict=checked["verdict"] if checked else heuristic_verdict
            feature_values.append(1.0 if verdict=="same" else 0.5 if verdict=="partial" else 0.0)
            coverage_by_feature[feature.id].append(feature_values[-1])
            quote=checked.get("evidence_quote") if checked else None
            evidence=({"chunk_id":repo_id+"#readme","snippet":quote,"source_url":repo["url"]} if quote else
                      extract_snippet(best,{"chunk_id":repo_id+"#readme","text":repo["readme"],"source_url":repo["url"]}) if verdict!="different" and best else {"status":"no evidence"})
            if "snippet" in evidence and not evidence_is_substring(evidence["snippet"], repo["readme"]):
                evidence = {"status": "no evidence"}
                verdict = "different"
                feature_values[-1] = 0.0
            if "snippet" in evidence:
                evidence_count += 1
            explanation=checked.get("explanation","") if checked else f"Lexical feature overlap is {raw:.2f}; this is a heuristic comparison."
            matches.append({"proposal_feature_id": feature.id, "repo_feature": best[:100], "verdict": verdict,
                            "explanation": explanation, "evidence": evidence})
        f_sim = sum(feature_values) / len(profile.features) if profile.features else 0
        tech_sim = similarity(" ".join(profile.tech_stack), " ".join(repo["topics"]))
        score = overall(p_sim, f_sim, tech_sim)
        notes = ["TF-IDF-style lexical matching is standing in for dense embeddings."]
        notes.append("Feature verdicts were LLM-verified." if verification_ran else "Feature verdicts are heuristic; no LLM verification ran.")
        readme_chars=len(repo["readme"])
        level="high" if readme_chars>=1500 and verification_ran and evidence_count>=2 else "medium" if readme_chars>=300 and (verification_ran or evidence_count>=1) else "low"
        outcome = label(score)
        if outcome in {"near_duplicate", "strong_overlap"} and (f_sim < 0.5 or evidence_count < 2):
            outcome = "partial_overlap" if score >= 40 else "related"
            notes.append("Strong-label guard applied: insufficient verified feature evidence.")
        if p_sim < 0.3 and f_sim < 0.2 and outcome in {"near_duplicate", "strong_overlap", "partial_overlap"}:
            outcome = "related"
            notes.append("Same-tech-only guard applied.")
        if outcome in {"near_duplicate", "strong_overlap"}:
            outcome = "partial_overlap"
            notes.append("Low-confidence label guard applied.")
        comparisons.append({"repo_id": repo_id, "title": repo["title"], "url": repo["url"], "stars": repo["stars"],
            "overall_overlap": round(score, 1), "label": outcome,
            "breakdown": {"problem_sim": round(p_sim, 3), "feature_overlap": round(f_sim, 3), "tech_overlap": round(tech_sim, 3)},
            "feature_matches": matches, "confidence": level, "notes": notes,
            "retrieval": {"rank_bm25": next((i for i,item in enumerate(retrieval_trace["rankings"]["bm25"],1) if item==repo_id),None),
                          "rank_dense": next((i for i,item in enumerate(retrieval_trace["rankings"]["dense"],1) if item==repo_id),None),
                          "rank_fused": next((i for i,item in enumerate(retrieval_trace["rankings"]["fused"],1) if item==repo_id),None), "rank_rerank": None}})
    stage("comparing", 0.7, f"Compared {len(comparisons)} repositories; evidence quotes passed the substring guard.")
    max_problem = max((item["breakdown"]["problem_sim"] for item in comparisons), default=0)
    feature_novelty = sum(1 - (sum(vals) / len(vals) if vals else 0) for vals in coverage_by_feature.values()) / max(1,len(profile.features))
    neighbor_distance = 1 - sum(item["overall_overlap"] for item in comparisons[:3]) / max(1, min(3,len(comparisons))) / 100
    stage("finding white space", 0.74, f"Checking the {len(repos)} indexed repositories against configured differentiation axes.")
    gap_templates = [
        ("G1", "language access", "Offer the core workflow in the languages used by the target community."),
        ("G2", "offline evaluation", "Measure whether recommendations are useful against a labeled set of proposals."),
        ("G3", "privacy controls", "Let teams inspect, export, and delete locally stored proposal data."),
        ("G4", "mentor workflow", "Give mentors a review flow that summarizes evidence across several proposals."),
        ("G5", "low-bandwidth use", "Keep the analysis usable when teams have intermittent network access."),
    ]
    proposal_gap_text=" ".join([profile.summary,*(feature.name+" "+feature.description for feature in profile.features)])
    threshold=config["novelty"]["gap_threshold"]
    gaps=[]
    for gid,angle,change in gap_templates:
        nearest=max((similarity(angle,repo["description"]+" "+" ".join(repo["topics"])+" "+repo["readme"]) for repo in repos),default=0.0)
        relevance=similarity(angle,profile.problem)
        occupied=similarity(angle,proposal_gap_text)>=threshold
        feasibility=0.8 if gid in {"G1","G3","G4"} else 0.55
        gap_score=.5*(1-nearest)+.3*relevance+.2*feasibility
        gaps.append({"gap_id":gid,"angle":angle,"change":change,"max_similarity":nearest,
                     "occupied":occupied,"gap_score":gap_score})
    gaps.sort(key=lambda gap:(gap["occupied"],-gap["gap_score"]))
    gaps=gaps[:config["recommendations"]["count"]]
    white_space = [{"gap_id":gap["gap_id"],"angle":gap["angle"],
        "why_open":f"Highest lexical similarity in the {len(comparisons)} compared demo repositories was {gap['max_similarity']:.2f}; this small corpus cannot establish global absence.",
        "supporting_gap":f"Candidate gap score {gap['gap_score']:.2f}; threshold {threshold:.2f}; corpus size {len(repos)}."} for gap in gaps]
    stage("writing recommendations", 0.83, "Grounding five template recommendations in the detected corpus gaps.")
    recommendations = [{"rank": i+1, "change": gap["change"], "why_distinctive": f"It explores the corpus gap around {gap['angle']} for {', '.join(profile.target_users)}.", "grounded_in_gap": gap["gap_id"], "effort": "S" if gap["gap_id"] in {"G1","G3"} else "M", "feasible_in_hackathon": gap["gap_id"]!="G5", "estimated_novelty_gain": "estimate; not yet calibrated"} for i,gap in enumerate(gaps)]
    whitespace_use=sum(similarity(gap["angle"],proposal_gap_text)>=threshold for gap in gaps)/max(1,len(gaps))
    novelty_weights=config["novelty"]["weights"]
    score_breakdown = {"problem_novelty": round(1-max_problem,3), "feature_novelty": round(feature_novelty,3),
        "neighbor_distance": round(neighbor_distance,3), "whitespace_use": whitespace_use,
        "weights": novelty_weights,
        "notes": ["The corpus is a tiny offline demo snapshot.", "Every score is heuristic; low novelty is not a judgment of idea quality."]}
    novelty = round(100*(novelty_weights["problem"]*score_breakdown["problem_novelty"]+novelty_weights["feature"]*feature_novelty+novelty_weights["neighbors"]*neighbor_distance+novelty_weights["whitespace"]*whitespace_use),1)
    unique = [{"feature_id":fid} for fid,vals in coverage_by_feature.items() if not any(vals)]
    commodity = [{"feature_id":fid,"covered_by":[c["repo_id"] for c in comparisons if any(m["proposal_feature_id"]==fid and m["verdict"] in ("same","partial") for m in c["feature_matches"])]} for fid,vals in coverage_by_feature.items() if sum(v>=.5 for v in vals)>=3]
    report = {"report_id":str(uuid.uuid4()),"created_at":datetime.now(timezone.utc).isoformat(),"input":text,
        "proposal_profile":profile.model_dump(mode="json"),"retrieval_trace":retrieval_trace | {"corpus_size":len(repos)},
        "comparisons":comparisons,"novelty_report":{"novelty_score":novelty,"score_breakdown":score_breakdown,"confidence":"low","commodity_features":commodity,"unique_features":unique,"white_space":white_space,"recommendations":recommendations},
        "config_snapshot":{"weights":{"problem":.35,"feature":.5,"tech":.15}},"provider_info":{"llm":extraction.source,"embedding":retrieval_trace["dense"]},"parent_report_id":parent_report_id,
        "warnings":[f"This report covers only the {len(repos)} repositories indexed locally; results are advisory and incomplete.","Idea-level similarity only; no source code is read or compared.","Heuristic feature verification and recommendation templates are active.",*extraction.warnings]}
    report = sanitize_generated(json.loads(json.dumps(report, default=str)))
    with connect() as db:
        db.execute("INSERT INTO reports(report_id,created_at,input_text,report_json,parent_report_id) VALUES(?,?,?,?,?)",
                   (report["report_id"],report["created_at"],text,json.dumps(report),parent_report_id))
    stage("done", 1.0, "Report stored locally.")
    return report
