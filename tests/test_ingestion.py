import json
import base64
from app import db
from app.ingestion import github_client
from app.ingestion import ingest as ingestion


class FakeResponse:
    headers={"ETag":"etag-1"}
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self): return b'{"cached":true}'


def test_github_etag_cache_serves_304_without_redownload(monkeypatch,tmp_path):
    monkeypatch.setattr(db,"DB_PATH",tmp_path/"github.sqlite3")
    db.init_db()
    calls=[]
    def fake_open(request,timeout,context):
        calls.append(request.headers)
        if len(calls)==1: return FakeResponse()
        assert request.headers["If-none-match"]=="etag-1"
        raise github_client.HTTPError(request.full_url,304,"not modified",{},None)
    monkeypatch.setattr(github_client,"urlopen",fake_open)
    assert github_client.request_json("https://api.github.test/data")=={"cached":True}
    assert github_client.request_json("https://api.github.test/data")=={"cached":True}
    assert len(calls)==2


def test_ingestion_cursor_resumes_without_reprocessing(monkeypatch,tmp_path):
    monkeypatch.setattr(db,"DB_PATH",tmp_path/"resume.sqlite3")
    db.init_db()
    entries=[{"full_name":"sample/one","html_url":"https://github.com/sample/one","name":"one","description":"first","topics":[],"stargazers_count":3},
             {"full_name":"sample/two","html_url":"https://github.com/sample/two","name":"two","description":"second","topics":[],"stargazers_count":4}]
    monkeypatch.setattr(ingestion,"search_repositories",lambda *args,**kwargs:entries)
    monkeypatch.setattr(ingestion,"get_readme",lambda *args:"# Project\n"+"Useful repository description. "*30)
    monkeypatch.setattr(ingestion,"rate_budget",lambda:{"remaining":12})
    first=ingestion.ingest_github(limit=1,queries=["test query"])
    second=ingestion.ingest_github(limit=1,queries=["test query"])
    assert first["added"]==1 and first["cursor"]["item"]==1
    assert second["added"]==1
    assert {r["repo_id"] for r in db.get_repos()}=={"sample/one","sample/two"}


def test_readme_decodes_github_base64(monkeypatch):
    content=base64.b64encode(b"# FigCraft\nA design tool.").decode()
    monkeypatch.setattr(github_client,"request_json",lambda url:{"encoding":"base64","content":content})
    assert github_client.get_readme("storytold","figcraft")=="# FigCraft\nA design tool."


def test_readme_missing_is_metadata_only(monkeypatch):
    def missing(url): raise github_client.GitHubError("GitHub returned HTTP 404 for a public API request.")
    monkeypatch.setattr(github_client,"request_json",missing)
    assert github_client.get_readme("storytold","figcraft")==""


def test_ingestion_skips_repositories_already_in_local_corpus(monkeypatch,tmp_path):
    monkeypatch.setattr(db,"DB_PATH",tmp_path/"dedupe.sqlite3")
    db.init_db()
    db.add_repo("sample/existing","https://github.com/sample/existing","existing","","Already here")
    monkeypatch.setattr(ingestion,"search_repositories",lambda *args,**kwargs:[{"full_name":"sample/existing"}])
    monkeypatch.setattr(ingestion,"rate_budget",lambda:{"remaining":10})
    result=ingestion.ingest_github(limit=1,queries=["test"])
    assert result["added"]==0 and result["skipped"]==1


def test_topic_import_adds_related_public_repo(monkeypatch,tmp_path):
    monkeypatch.setattr(db,"DB_PATH",tmp_path/"topic.sqlite3")
    db.init_db()
    monkeypatch.setattr(ingestion,"search_repositories",lambda query,per_page:[{
        "full_name":"storytold/figcraft","html_url":"https://github.com/storytold/figcraft",
        "name":"figcraft","description":"Design and prototyping","topics":["design"],
        "stargazers_count":5,"language":"Rust","license":{"spdx_id":"MIT"}}])
    monkeypatch.setattr(ingestion,"get_readme",lambda *args:"# FigCraft\n"+"Design and prototype interfaces. "*20)
    monkeypatch.setattr(ingestion,"rate_budget",lambda:{"remaining":10})
    result=ingestion.ingest_topic("interface design prototyping",limit=5)
    assert result["added"]==1
    assert db.get_repos()[0]["repo_id"]=="storytold/figcraft"
    assert db.chunk_count()>0
