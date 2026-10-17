"""Fetch readable public web pages for local IdeaCheck review, with SSRF guards."""
from __future__ import annotations

import ipaddress
import html
import re
import ssl
import socket
import certifi
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, Request, build_opener

MAX_BYTES = 1_500_000
MAX_TEXT_CHARS = 20_000
TIMEOUT_SECONDS = 75  # allow cold-started public hosts such as Render time to wake up
ALLOWED_TYPES = {"text/html", "application/xhtml+xml", "text/plain", "text/markdown", "application/json"}


class URLReviewError(ValueError):
    """A URL could not be safely fetched or did not contain reviewable text."""


def validate_public_url(url: str) -> str:
    try:
        parsed = urlsplit(url.strip())
        port = parsed.port
    except ValueError as exc:
        raise URLReviewError("That URL is malformed.") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise URLReviewError("Enter a complete public website URL beginning with http:// or https://.")
    if parsed.username or parsed.password:
        raise URLReviewError("URLs containing usernames or passwords are not accepted.")
    if port not in {None, 80, 443}:
        raise URLReviewError("For safety, only the standard website ports 80 and 443 are accepted.")
    host = parsed.hostname.rstrip(".").casefold()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise URLReviewError("Local and internal network addresses cannot be reviewed.")
    try:
        addresses = {ipaddress.ip_address(host)} if _is_ip(host) else {
            ipaddress.ip_address(result[4][0]) for result in socket.getaddrinfo(host, port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        }
    except (OSError, ValueError) as exc:
        raise URLReviewError("The website address could not be resolved. Check the URL and try again.") from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise URLReviewError("The URL must resolve only to a public internet address.")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


class _SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        validate_public_url(urljoin(request.full_url, newurl))
        return super().redirect_request(request, response, code, message, headers, newurl)


class _PageText(HTMLParser):
    SKIP = {"script", "style", "svg", "nav", "footer", "header", "noscript", "iframe", "template"}
    BLOCKS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "blockquote", "td", "th", "dt", "dd"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.title_depth = 0
        self.title = []
        self.description = ""
        self.parts: list[str] = []
        self.current: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.SKIP or attrs.get("role", "").casefold() == "navigation" or attrs.get("aria-label", "").casefold() in {"navigation", "main navigation", "site navigation"}:
            self.skip_depth += 1
        if tag == "title":
            self.title_depth += 1
        if tag == "meta" and (attrs.get("name", "").casefold() == "description" or attrs.get("property", "").casefold() == "og:description"):
            self.description = attrs.get("content", "").strip()[:1000]
        if tag in self.BLOCKS and not self.skip_depth:
            self._flush()
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and not self.skip_depth:
            self.current.append("#" * int(tag[1]))

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip_depth:
            self.skip_depth -= 1
        if tag == "title" and self.title_depth:
            self.title_depth -= 1
        if tag in self.BLOCKS and not self.skip_depth:
            self._flush()

    def handle_data(self, data):
        clean = " ".join(data.split())
        if not clean:
            return
        if self.title_depth:
            self.title.append(clean)
        if not self.skip_depth:
            self.current.append(clean)

    def _flush(self):
        value = " ".join(self.current).strip()
        if value:
            self.parts.append(value)
        self.current.clear()

    def result(self) -> tuple[str, str]:
        self._flush()
        title = " ".join(self.title).strip()
        text = "\n".join(dict.fromkeys(self.parts))
        if len(text) < 120 and self.description:
            text = f"{text}\n\nPage description: {self.description}".strip()
        return title, text[:MAX_TEXT_CHARS]


def extract_page_text(body: bytes, content_type: str) -> tuple[str, str]:
    charset = "utf-8"
    for item in content_type.split(";")[1:]:
        key, _, value = item.strip().partition("=")
        if key.casefold() == "charset" and value.strip('"'):
            charset = value.strip('"')
    try:
        decoded = body.decode(charset, errors="replace")
    except LookupError:
        decoded = body.decode("utf-8", errors="replace")
    if "html" not in content_type.casefold() and "xhtml" not in content_type.casefold():
        return "", _remove_route_catalog_rows(decoded)[:MAX_TEXT_CHARS].strip()
    parser = _PageText()
    parser.feed(decoded)
    return parser.result()


_ROUTE = re.compile(r"(?:^|\s)/(?:[a-z][\w-]*|<[^>]+>)(?:/(?:[\w-]+|<[^>]+>))*", re.I)
_NAV_LABELS = (
    "overview", "staff console", "analytics", "what-if", "what if", "setup",
    "look & feel", "look and feel", "qr poster", "dashboard", "settings",
)


def _remove_route_catalog_rows(text: str) -> str:
    """Clean Markdown noise and omit route tables that add navigation, not project evidence."""
    kept = []
    table_is_navigation = False
    for line in text.splitlines():
        stripped = line.strip()
        if "|" in stripped:
            cells = [cell.strip().strip("`*_ ") for cell in stripped.strip("|").split("|")]
            searchable = " ".join(cells).casefold()
            labels = sum(label in searchable for label in _NAV_LABELS)
            is_separator = all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells if cell)
            if not table_is_navigation and len(cells) >= 3 and any(word in searchable for word in ("website", "websites", "who uses it", "address")):
                table_is_navigation = True
            # A route/menu list is presentation material. Drop its header, rows, and
            # separator together; retain unrelated tables such as feature matrices.
            if table_is_navigation:
                if not stripped or is_separator:
                    continue
                if not re.search(r"\|", stripped):
                    table_is_navigation = False
                else:
                    continue
            # Also catch standalone navigation catalogs without a descriptive header.
            if _ROUTE.search(stripped) and labels >= 3 and len(cells) >= 3 and not re.search(r"[.!?]", stripped):
                continue
        else:
            table_is_navigation = False
        # Remove common Markdown presentation marks so citations read like prose.
        clean = html.unescape(stripped)
        clean = re.sub(r"^\s{0,3}#{1,6}\s+", "", clean)
        clean = re.sub(r"\*\*(.*?)\*\*|__(.*?)__", lambda m: m.group(1) or m.group(2), clean)
        clean = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)|(?<!_)_([^_]+)_(?!_)", lambda m: m.group(1) or m.group(2), clean)
        clean = re.sub(r"`([^`]+)`", r"\1", clean)
        clean = re.sub(r"\[([^\]]+)\]\((?:[^()]|\([^()]*\))*\)", r"\1", clean)
        kept.append(clean)
    return "\n".join(kept)


def _download(url: str) -> tuple[bytes, str, str, str]:
    safe_url = validate_public_url(url)
    request = Request(safe_url, headers={"User-Agent": "IdeaCheck/0.2 (public project review)", "Accept": "text/html,application/xhtml+xml,text/plain,text/markdown,application/json;q=0.9"})
    tls = ssl.create_default_context(cafile=certifi.where())
    opener = build_opener(_SafeRedirect(), HTTPSHandler(context=tls))
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            full_content_type = response.headers.get("Content-Type", "")
            content_type = full_content_type.split(";", 1)[0].strip().casefold()
            if content_type not in ALLOWED_TYPES:
                raise URLReviewError(f"This page returned {content_type or 'an unknown content type'}; only readable HTML, text, Markdown, or JSON is supported.")
            declared = response.headers.get("Content-Length")
            try:
                if declared and int(declared) > MAX_BYTES:
                    raise URLReviewError("This page is too large to review (limit: 1.5 MB).")
            except ValueError as exc:
                raise URLReviewError("The website returned an invalid content length.") from exc
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise URLReviewError("This page is too large to review (limit: 1.5 MB).")
            return body, content_type, full_content_type, response.geturl()
    except HTTPError as exc:
        raise URLReviewError(f"The website returned HTTP {exc.code}. Make sure it is public and try again.") from exc
    except URLError as exc:
        reason = exc.reason
        if isinstance(reason, ssl.SSLCertVerificationError):
            message = "TLS certificate verification failed. Install or update the Python certificate bundle, then retry."
        elif isinstance(reason, socket.gaierror):
            message = "DNS could not resolve the website. Check your internet connection and URL."
        elif isinstance(reason, (TimeoutError, socket.timeout)):
            message = "The website took too long to respond. A sleeping Render service may need another try."
        else:
            message = f"Could not connect to the website ({str(reason)[:180]}). Check your internet connection and retry."
        raise URLReviewError(message) from exc
    except TimeoutError as exc:
        raise URLReviewError("The website took too long to respond. A sleeping Render service may need another try.") from exc


def _github_readme(owner: str, repo: str, original_url: str) -> dict | None:
    """Prefer a raw repository README to GitHub's large navigation HTML."""
    last_error = None
    for branch in ("main", "master"):
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md"
        try:
            body, content_type, full_type, _ = _download(raw_url)
        except URLReviewError as exc:
            last_error = exc
            if "HTTP 404" in str(exc):
                continue
            return None
        _, text = extract_page_text(body, full_type or content_type)
        match = re.search(r"(?m)^#\s+(.+?)\s*$", text)
        title = match.group(1).strip() if match else f"{owner}/{repo} README"
        if len(text) >= 120:
            return {"title": title, "text": text[:MAX_TEXT_CHARS], "url": original_url, "content_type": content_type, "source_detail": "repository README"}
    if last_error and "HTTP 404" not in str(last_error):
        raise last_error
    return None


def fetch_reviewable_page(url: str) -> dict:
    """Fetch a public page (or a GitHub repository README) for local review."""
    safe_url = validate_public_url(url)
    parsed_input = urlsplit(safe_url)
    path_parts = [part for part in parsed_input.path.split("/") if part]
    display_input_url = urlunsplit((parsed_input.scheme, parsed_input.netloc, parsed_input.path, "", ""))
    if parsed_input.hostname.casefold() in {"github.com", "www.github.com"} and len(path_parts) == 2:
        readme = _github_readme(path_parts[0], path_parts[1], display_input_url)
        if readme:
            return readme

    body, content_type, full_content_type, final_url = _download(safe_url)
    title, text = extract_page_text(body, full_content_type)
    if len(text) < 120:
        raise URLReviewError("The page did not expose enough readable text for a useful review. It may require JavaScript or authentication; try its README, project description, or requirements page.")
    parsed = urlsplit(final_url)
    display_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    return {"title": title or parsed.hostname or "Project page", "text": text, "url": display_url, "content_type": content_type, "source_detail": "public webpage"}
