from app.retrieval.fusion import reciprocal_rank_fusion


def test_rrf_hand_calculated_order_and_ties():
    result = reciprocal_rank_fusion([["a", "b"], ["b", "a"]], 60)
    assert [item for item, _ in result] == ["a", "b"]  # stable ID breaks exact ties
    result = reciprocal_rank_fusion([["a", "b"], ["b", "c"]], 60)
    assert result[0][0] == "b"
