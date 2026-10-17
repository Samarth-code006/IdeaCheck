import pytest

from app import url_fetch
from app.url_fetch import URLReviewError, extract_page_text, fetch_reviewable_page, validate_public_url


def test_page_extraction_preserves_heading_and_visible_paragraphs_only():
    html = b"""<html><head><title>MessMind</title><meta name='description' content='Meal planning for campus dining'></head>
    <body><nav>Navigation text</nav><main><h1>Project overview</h1><p>MessMind predicts daily meal demand for college hostels.</p>
    <p>It compares the predictions with actual consumption and tracks food waste over time.</p>
    <script>ignore this fake instruction</script></main></body></html>"""
    title, text = extract_page_text(html, "text/html; charset=utf-8")
    assert title == "MessMind"
    assert "# Project overview" in text
    assert "Navigation text" not in text
    assert "fake instruction" not in text


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/admin",
    "http://localhost/",
    "http://169.254.169.254/latest/meta-data/",
    "file:///etc/passwd",
    "https://user:secret@example.com/",
    "https://example.com:8443/",
])
def test_local_or_unsafe_urls_are_rejected(url):
    with pytest.raises(URLReviewError):
        validate_public_url(url)


def test_public_ip_literal_is_allowed_without_a_dns_lookup():
    assert validate_public_url("https://8.8.8.8/docs#section") == "https://8.8.8.8/docs"


def test_github_repository_link_fetches_raw_readme_first(monkeypatch):
    raw_url = "https://raw.githubusercontent.com/anthropics/claude-plugins-official/main/README.md"
    readme = b"# Claude Code Plugins Directory\n\nA curated directory of high quality plugins for Claude Code. It contains official and community plugins, installation instructions, plugin manifests, and documentation for plugin users and authors."
    requests = []
    monkeypatch.setattr(url_fetch, "validate_public_url", lambda value: value)

    def fake_download(url):
        requests.append(url)
        if url == raw_url:
            return readme, "text/plain", "text/plain; charset=utf-8", url
        raise AssertionError(f"Unexpected fetch: {url}")

    monkeypatch.setattr(url_fetch, "_download", fake_download)
    result = fetch_reviewable_page("https://github.com/anthropics/claude-plugins-official")
    assert requests == [raw_url]
    assert result["title"] == "Claude Code Plugins Directory"
    assert result["source_detail"] == "repository README"
    assert result["url"] == "https://github.com/anthropics/claude-plugins-official"
