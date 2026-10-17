"""Lightweight README cleaner and heading-aware chunker."""
import html
import re


def chunk_readme(repo_id: str, markdown: str, max_chars: int = 1200) -> list[dict]:
    text = html.unescape(re.sub(r"<[^>]+>", " ", markdown or ""))
    lines = [re.sub(r"!\[[^]]*\]\([^)]*\)", "", line).strip() for line in text.splitlines()]
    chunks, section, buffer, count = [], "Overview", [], 0
    for line in lines:
        if line.startswith("#"):
            if buffer:
                chunks.append({"chunk_id": f"{repo_id}#{count:03d}", "section": section, "text": " ".join(buffer)[:max_chars]})
                count += 1
            section, buffer = line.lstrip("# ")[:80] or "Overview", []
        elif line:
            buffer.append(line)
            if sum(len(part) for part in buffer) >= max_chars:
                chunks.append({"chunk_id": f"{repo_id}#{count:03d}", "section": section, "text": " ".join(buffer)[:max_chars]})
                count += 1
                buffer = []
    if buffer:
        chunks.append({"chunk_id": f"{repo_id}#{count:03d}", "section": section, "text": " ".join(buffer)[:max_chars]})
    return chunks
