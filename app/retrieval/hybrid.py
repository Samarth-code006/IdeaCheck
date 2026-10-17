"""Selectable BM25, TF-IDF cosine, hybrid RRF, and optional rerank modes."""
from app.retrieval.bm25 import rank as bm25_rank
from app.retrieval.dense import rank as dense_rank
from app.retrieval.fusion import reciprocal_rank_fusion
from app.config import get_config

MODES={"bm25","dense","hybrid","hybrid_rerank"}


def retrieve(query: str, documents: list[dict], mode: str = "hybrid", final_k: int = 10) -> tuple[list[dict],dict]:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(sorted(MODES))}")
    config=get_config()
    k=max(config["retrieval"]["bm25_k"],len(documents))
    def aggregate(rows):
        best={}
        for row in rows:
            repo_id=row["repo_id"]
            if repo_id not in best or row["score"]>best[repo_id]["score"]:
                best[repo_id]=row
        return sorted(best.values(),key=lambda row:(-row["score"],row["repo_id"]))
    bm25=aggregate(bm25_rank(query,documents,k)) if mode in ("bm25", "hybrid", "hybrid_rerank") else []
    dense=aggregate(dense_rank(query,documents,k)) if mode in ("dense", "hybrid", "hybrid_rerank") else []
    if mode=="bm25":
        selected=bm25
    elif mode=="dense":
        selected=dense
    else:
        fused=reciprocal_rank_fusion([[row["repo_id"] for row in bm25],[row["repo_id"] for row in dense]],config["retrieval"]["rrf_k"])
        by_id={}
        for row in documents: by_id.setdefault(row["repo_id"],row)
        selected=[dict(by_id[item],score=score) for item,score in fused]
    # The cross-encoder is optional and currently absent. Never label the lexical
    # reordering as ML reranking; expose the requested mode and the fallback.
    from app.providers.factory import get_embedding_provider
    embedder=get_embedding_provider()
    dense_label="TF-IDF cosine (lexical fallback)" if embedder.name=="tfidf" else f"{embedder.name}: {embedder.model}"
    trace={"mode":mode,"bm25":"BM25","dense":dense_label,
           "fusion":"RRF" if mode in ("hybrid","hybrid_rerank") else "not used",
           "reranker":"unavailable; hybrid order retained" if mode=="hybrid_rerank" else "not requested",
           "rankings":{"bm25":[r["repo_id"] for r in bm25],"dense":[r["repo_id"] for r in dense],
                       "fused":[r["repo_id"] for r in selected] if mode in ("hybrid","hybrid_rerank") else [],"rerank":[]}}
    return selected[:final_k],trace
