from app.compare.scoring import label, overall, similarity


def test_scoring_bounds_and_labels():
    assert overall(1, 1, 1) == 100
    assert overall(-2, 1, 1) == 0
    assert label(85) == "near_duplicate"
    assert label(10) == "distinct"
    assert similarity("offline clinic booking", "clinic appointment booking") > 0
