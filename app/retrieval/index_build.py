"""Build a persistent SQLite inverted index over README chunks and repo metadata."""
from datetime import datetime,timezone
from collections import Counter
from app.db import connect,init_db,get_repos,get_chunks,save_chunk
from app.extraction.chunking import chunk_readme
from app.retrieval.bm25 import tokenize


def build_index()->dict:
    init_db()
    repos=get_repos()
    chunks=get_chunks()
    grouped={}
    for chunk in chunks: grouped.setdefault(chunk["repo_id"],[]).append(chunk)
    for repo in repos:
        if repo["repo_id"] not in grouped:
            for chunk in chunk_readme(repo["repo_id"],repo["readme"]):
                save_chunk(repo["repo_id"],chunk)
    chunks=get_chunks()
    rows=[]
    for chunk in chunks:
        terms=Counter(tokenize(chunk["text"]))
        for term,count in terms.items():
            rows.append((term,chunk["chunk_id"],chunk["repo_id"],count,sum(terms.values())))
    now=datetime.now(timezone.utc).isoformat()
    with connect() as db:
        db.execute("DELETE FROM bm25_terms")
        db.executemany("INSERT INTO bm25_terms(token,chunk_id,repo_id,term_frequency,document_length) VALUES(?,?,?,?,?)",rows)
        db.execute("INSERT OR REPLACE INTO index_metadata(index_name,document_count,term_count,built_at) VALUES('bm25',?,?,?)",(len(chunks),len(rows),now))
    return {"repos":len(repos),"chunks":len(chunks),"term_postings":len(rows),"built_at":now}


if __name__=="__main__":
    print(build_index())
