from app.pipeline import safe_text


def test_banned_generated_language_is_dropped():
    assert safe_text("A recommendation has evidence.") == "A recommendation has evidence."
    assert safe_text("This project was copied by another team.") == ""
