import pytest
from app.retrieval.hybrid import retrieve


def test_all_retrieval_modes_return_ranked_results_and_trace():
    docs=[{"repo_id":"a","text":"idea similarity feature evidence"},
          {"repo_id":"b","text":"student timetable course scheduling"}]
    for mode in ("bm25","dense","hybrid","hybrid_rerank"):
        results,trace=retrieve("idea similarity",docs,mode,2)
        assert results[0]["repo_id"]=="a"
        assert trace["mode"]==mode
    assert "unavailable" in retrieve("idea similarity",docs,"hybrid_rerank")[1]["reranker"]


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        retrieve("idea",[],"mystery")
