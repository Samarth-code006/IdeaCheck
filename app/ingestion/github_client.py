"""GitHub REST API client with ETag caching, budget reporting, and bounded retries."""
import base64
import json
import os
import random
import ssl
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import certifi
from app.db import connect
from app.config import get_config

API = "https://api.github.com"
USER_AGENT = "novelty-coach-hackathon/0.1"
class GitHubError(RuntimeError):
    pass


def request_json(url: str) -> dict:
    """Make a public API request, replaying a cached body on 304 or transient failure."""
    with connect() as db:
        cached = db.execute("SELECT etag,response_json FROM github_cache WHERE url=?",(url,)).fetchone()
    headers = {"Accept":"application/vnd.github+json","User-Agent":USER_AGENT,"X-GitHub-Api-Version":"2022-11-28"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if cached and cached[0]:
        headers["If-None-Match"] = cached[0]
    settings=get_config()["github"]
    retries=settings["retry_attempts"]
    for attempt in range(retries):
        try:
            tls_context=ssl.create_default_context(cafile=certifi.where())
            with urlopen(Request(url,headers=headers),timeout=settings["timeout_seconds"],context=tls_context) as response:
                raw = response.read()
                body = json.loads(raw or b"{}")
                etag = response.headers.get("ETag")
                with connect() as db:
                    db.execute("INSERT OR REPLACE INTO github_cache(url,etag,response_json,updated_at) VALUES(?,?,?,?)",
                               (url,etag,json.dumps(body),datetime.now(timezone.utc).isoformat()))
                return body
        except HTTPError as exc:
            if exc.code == 304 and cached:
                return json.loads(cached[1])
            retry_after=exc.headers.get("Retry-After") if exc.headers else None
            if retry_after and attempt<retries-1:
                time.sleep(max(1,min(float(retry_after),settings["max_backoff_seconds"])))
                continue
            if exc.code in (403,429) and exc.headers.get("X-RateLimit-Remaining") == "0":
                reset = int(exc.headers.get("X-RateLimit-Reset",time.time()+60))
                wait = max(1,min(reset-time.time()+1,60))
                if attempt < retries-1:
                    time.sleep(wait)
                    continue
                raise GitHubError("GitHub API rate limit reached. Add a token or retry after the reset time.") from exc
            if exc.code >= 500 and attempt < retries-1:
                time.sleep(min(2 ** attempt + random.random(),settings["max_backoff_seconds"]))
                continue
            raise GitHubError(f"GitHub returned HTTP {exc.code} for a public API request.") from exc
        except (URLError,TimeoutError) as exc:
            if attempt < retries-1:
                time.sleep(min(2 ** attempt + random.random(),settings["max_backoff_seconds"]))
                continue
            if cached:
                return json.loads(cached[1])
            reason = getattr(exc, "reason", exc)
            raise GitHubError(
                "Could not connect to GitHub's API after retries, and this request is not cached "
                f"({type(reason).__name__}: {reason}). Check the Python runtime's network or TLS setup, then retry."
            ) from exc
    raise GitHubError("GitHub request failed after bounded retries.")


def search_repositories(query: str, page: int = 1, per_page: int | None = None) -> list[dict]:
    from urllib.parse import urlencode
    per_page=per_page or get_config()["github"]["per_page"]
    params=urlencode({"q":query+" fork:false archived:false","sort":"stars","order":"desc","page":page,"per_page":per_page})
    result=request_json(f"{API}/search/repositories?{params}")
    return result.get("items",[])


def get_readme(owner: str, name: str) -> str:
    try:
        result=request_json(f"{API}/repos/{owner}/{name}/readme")
    except GitHubError as exc:
        # A public repository may have no README. Metadata is still useful.
        if "HTTP 404" in str(exc):
            return ""
        raise
    if result.get("encoding") != "base64":
        return ""
    try:
        return base64.b64decode(result.get("content", "")).decode("utf-8", errors="replace")
    except (ValueError, UnicodeError):
        return ""


def fetch_repository(owner: str, name: str) -> dict:
    """Fetch public repository metadata, rejecting private/missing targets via API."""
    result=request_json(f"{API}/repos/{owner}/{name}")
    if result.get("private"):
        raise GitHubError("That repository is private. Enter a public GitHub repository URL.")
    return result


def rate_budget() -> dict:
    try:
        result=request_json(f"{API}/rate_limit")
        return result.get("resources",{}).get("core",{})
    except GitHubError as exc:
        return {"unavailable":str(exc)}
