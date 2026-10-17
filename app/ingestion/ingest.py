"""Loads the offline snapshot and performs resumable public GitHub ingestion."""
import argparse
import json
from app.config import ROOT
from app.config import get_config
from app.db import add_repo, get_repos, save_chunk, connect
from app.extraction.chunking import chunk_readme
from app.ingestion.github_client import GitHubError, get_readme, rate_budget, search_repositories
from app.ingestion.seed_queries import SEED_QUERIES


def seed_demo_corpus() -> int:
    rows = json.loads((ROOT / "data" / "demo_corpus.json").read_text())
    existing = {row["repo_id"] for row in get_repos()}
    for row in rows:
        if row["repo_id"] not in existing:
            add_repo(row["repo_id"], row["url"], row["title"], row["description"], row["readme"], row["topics"])
        for chunk in chunk_readme(row["repo_id"],row["readme"]):
            save_chunk(row["repo_id"],chunk)
    return len(rows)


def ingest_topic(query: str, limit: int = 20) -> dict:
    """Fetch a bounded set of public repositories for a user-selected topic."""
    from app.db import get_repos
    items=search_repositories(query,per_page=min(100,max(limit*3,limit)))
    existing={repo["repo_id"].lower() for repo in get_repos()}
    added,skipped,errors=0,0,[]
    for repo in items:
        full_name=repo.get("full_name","").lower()
        if repo.get("fork") or repo.get("archived") or repo.get("private") or "/" not in full_name or full_name in existing:
            skipped+=1
            continue
        owner,name=full_name.split("/",1)
        try:
            readme=get_readme(owner,name)
            if len(readme.strip())<get_config()["github"]["min_readme_chars"]:
                skipped+=1
                continue
            add_repo(full_name,repo.get("html_url",f"https://github.com/{full_name}"),repo.get("name",name),
                repo.get("description") or "",readme,repo.get("topics") or [],repo.get("stargazers_count",0),
                [repo.get("language")] if repo.get("language") else [],
                (repo.get("license") or {}).get("spdx_id"),repo.get("updated_at",""))
            for chunk in chunk_readme(full_name,readme):
                save_chunk(full_name,chunk)
            existing.add(full_name)
            added+=1
            if added>=limit:
                break
        except GitHubError as exc:
            errors.append(f"{full_name}: {exc}")
            if "rate limit" in str(exc).lower() or "unreachable" in str(exc).lower():
                break
    return {"added":added,"skipped":skipped,"query":query,"rate_budget":rate_budget(),"errors":errors}


def ingest_github(limit: int = 20, queries: list[str] | None = None) -> dict:
    """Fetch public repo metadata and README text, checkpointing after each item."""
    init=get_config()["github"]
    queries=queries or SEED_QUERIES
    with connect() as db:
        state=db.execute("SELECT state_value FROM ingestion_state WHERE state_key='github_cursor'").fetchone()
    cursor=json.loads(state[0]) if state else {"query":0,"page":1,"item":0}
    existing={repo["repo_id"].lower() for repo in get_repos()}
    added,skipped,errors=0,0,[]
    while cursor["query"] < len(queries) and added < limit:
        query=queries[cursor["query"]]
        try:
            items=search_repositories(query,page=cursor["page"],per_page=init["per_page"])
        except GitHubError as exc:
            errors.append(str(exc))
            break
        if cursor["item"] >= len(items):
            if len(items) < init["per_page"] or cursor["page"] >= init["max_pages_per_query"]:
                cursor={"query":cursor["query"]+1,"page":1,"item":0}
            else:
                cursor={"query":cursor["query"],"page":cursor["page"]+1,"item":0}
            continue
        repo=items[cursor["item"]]
        cursor["item"]+=1
        if repo.get("fork") or repo.get("archived") or repo.get("private"):
            skipped+=1
        else:
            full_name=repo.get("full_name","").lower()
            if "/" not in full_name or full_name in existing:
                skipped+=1
            else:
                owner,name=full_name.split("/",1)
                try:
                    readme=get_readme(owner,name)
                    if len(readme.strip()) < init["min_readme_chars"]:
                        skipped+=1
                    else:
                        add_repo(full_name,repo.get("html_url",f"https://github.com/{full_name}"),
                          repo.get("name",name),repo.get("description") or "",readme,
                          repo.get("topics") or [],repo.get("stargazers_count",0),
                          [repo.get("language")] if repo.get("language") else [],
                          (repo.get("license") or {}).get("spdx_id"),repo.get("updated_at", ""))
                        chunks=chunk_readme(full_name,readme)
                        for chunk in chunks:
                            save_chunk(full_name,chunk)
                        existing.add(full_name)
                        added+=1
                except GitHubError as exc:
                    errors.append(f"{full_name}: {exc}")
                    if "rate limit" in str(exc).lower() or "unreachable" in str(exc).lower():
                        cursor["item"]-=1
                        with connect() as db:
                            db.execute("INSERT OR REPLACE INTO ingestion_state(state_key,state_value) VALUES('github_cursor',?)",(json.dumps(cursor),))
                        break
        with connect() as db:
            db.execute("INSERT OR REPLACE INTO ingestion_state(state_key,state_value) VALUES('github_cursor',?)",(json.dumps(cursor),))
    return {"added":added,"skipped":skipped,"cursor":cursor,"rate_budget":rate_budget(),"errors":errors}


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description="Resumable public GitHub corpus ingestion")
    parser.add_argument("--limit",type=int,default=20)
    args=parser.parse_args()
    from app.db import init_db
    init_db()
    seed_demo_corpus()
    print(json.dumps(ingest_github(args.limit),indent=2))
