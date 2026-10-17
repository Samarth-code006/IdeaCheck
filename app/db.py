"""Small SQLite store for corpus metadata, reports, and deterministic provider cache."""
import json
import sqlite3
from pathlib import Path
from app.config import ROOT

DB_PATH = ROOT / "data" / "novelty_coach.sqlite3"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH,timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db() -> None:
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS repos (
          repo_id TEXT PRIMARY KEY, url TEXT NOT NULL, title TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '', topics TEXT NOT NULL DEFAULT '[]',
          languages TEXT NOT NULL DEFAULT '[]', license TEXT, stars INTEGER NOT NULL DEFAULT 0, readme TEXT NOT NULL DEFAULT '',
          updated_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS reports (
          report_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, input_text TEXT NOT NULL,
          report_json TEXT NOT NULL, parent_report_id TEXT
        );
        CREATE TABLE IF NOT EXISTS llm_cache (
          cache_key TEXT PRIMARY KEY, response_json TEXT NOT NULL, created_at TEXT NOT NULL,
          latency_ms INTEGER NOT NULL DEFAULT 0, tokens_in INTEGER, tokens_out INTEGER
        );
        CREATE TABLE IF NOT EXISTS embedding_cache (
          model TEXT NOT NULL, text_hash TEXT NOT NULL, vector_json TEXT NOT NULL,
          PRIMARY KEY(model, text_hash)
        );
        CREATE TABLE IF NOT EXISTS github_cache (
          url TEXT PRIMARY KEY, etag TEXT, response_json TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ingestion_state (
          state_key TEXT PRIMARY KEY, state_value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS repo_chunks (
          chunk_id TEXT PRIMARY KEY, repo_id TEXT NOT NULL, section TEXT NOT NULL,
          text TEXT NOT NULL, FOREIGN KEY(repo_id) REFERENCES repos(repo_id)
        );
        CREATE TABLE IF NOT EXISTS bm25_terms (
          token TEXT NOT NULL, chunk_id TEXT NOT NULL, repo_id TEXT NOT NULL,
          term_frequency INTEGER NOT NULL, document_length INTEGER NOT NULL,
          PRIMARY KEY(token,chunk_id)
        );
        CREATE INDEX IF NOT EXISTS idx_bm25_token ON bm25_terms(token);
        CREATE TABLE IF NOT EXISTS index_metadata (
          index_name TEXT PRIMARY KEY, document_count INTEGER NOT NULL,
          term_count INTEGER NOT NULL, built_at TEXT NOT NULL
        );
        """)
        # Upgrade databases created by earlier Novelty Coach builds in place.
        columns = {row[1] for row in db.execute("PRAGMA table_info(repos)")}
        if "languages" not in columns:
            db.execute("ALTER TABLE repos ADD COLUMN languages TEXT NOT NULL DEFAULT '[]'")
        if "license" not in columns:
            db.execute("ALTER TABLE repos ADD COLUMN license TEXT")


def add_repo(repo_id: str, url: str, title: str, description: str, readme: str,
             topics: list[str] | None = None, stars: int = 0, languages: list[str] | None = None,
             license_name: str | None = None, updated_at: str = "") -> None:
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO repos(repo_id,url,title,description,topics,languages,license,stars,readme,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (repo_id, url, title, description, json.dumps(topics or []),json.dumps(languages or []),license_name,stars,readme,updated_at))


def get_repos() -> list[dict]:
    with connect() as db:
        return [dict(row) | {"topics": json.loads(row["topics"]),"languages":json.loads(row["languages"] or "[]")} for row in db.execute("SELECT * FROM repos ORDER BY repo_id")]


def save_chunk(repo_id: str, chunk: dict) -> None:
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO repo_chunks(chunk_id,repo_id,section,text) VALUES(?,?,?,?)",
                   (chunk["chunk_id"],repo_id,chunk["section"],chunk["text"]))


def get_chunks() -> list[dict]:
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM repo_chunks ORDER BY repo_id,chunk_id")]


def chunk_count() -> int:
    with connect() as db:
        return db.execute("SELECT COUNT(*) FROM repo_chunks").fetchone()[0]
