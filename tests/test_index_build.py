from app import db
from app.ingestion.ingest import seed_demo_corpus
from app.retrieval.index_build import build_index
import sqlite3
import json
from pathlib import Path


def test_build_index_persists_chunk_terms(monkeypatch,tmp_path):
    monkeypatch.setattr(db,"DB_PATH",tmp_path/"index.sqlite3")
    db.init_db()
    seed_demo_corpus()
    result=build_index()
    assert result["repos"]==len(json.loads((Path(__file__).resolve().parents[1]/"data"/"demo_corpus.json").read_text()))
    assert result["chunks"]>=2
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM bm25_terms").fetchone()[0]>0


def test_init_db_upgrades_legacy_repo_table(monkeypatch,tmp_path):
    path=tmp_path/"legacy.sqlite3"
    monkeypatch.setattr(db,"DB_PATH",path)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE repos (repo_id TEXT PRIMARY KEY,url TEXT NOT NULL,title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',topics TEXT NOT NULL DEFAULT '[]',stars INTEGER NOT NULL DEFAULT 0,readme TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL DEFAULT '')")
        conn.execute("INSERT INTO repos(repo_id,url,title) VALUES('old','https://example.com','Old')")
    db.init_db()
    assert db.get_repos()[0]["languages"]==[]
    db.add_repo("new","https://example.com/new","New","","text",languages=["Python"])
    assert next(repo for repo in db.get_repos() if repo["repo_id"]=="new")["languages"]==["Python"]
