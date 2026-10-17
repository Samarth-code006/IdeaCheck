#!/usr/bin/env python3
"""Report local build capabilities without exposing credentials."""
import importlib.util
import os
import platform
import shutil
import socket
import subprocess
import sys
import urllib.request


def reachable(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status < 500
    except Exception:
        return False


def main() -> None:
    stats = shutil.disk_usage(".")
    ram = None
    if hasattr(os, "sysconf"):
        try:
            ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        except (ValueError, OSError):
            pass
    pip = subprocess.run([sys.executable, "-m", "pip", "install", "--dry-run", "--no-deps", "--no-index", "-r", "requirements.txt"], capture_output=True, text=True)
    hf_cache = os.path.expanduser("~/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2")
    hf_cached = os.path.isdir(hf_cache)
    print(f"Python: {platform.python_version()} ({sys.executable}) | OS: {platform.platform()}")
    print(f"CPU: {os.cpu_count() or 'unknown'} cores | RAM: {round(ram / 1024**3, 1) if ram else 'unknown'} GB | Free disk: {stats.free / 1024**3:.1f} GB")
    print(f"pip: {'available' if importlib.util.find_spec('pip') else 'unavailable'} | offline dependency resolution: {'passed' if pip.returncode == 0 else 'failed (packages absent from local cache)'} | GitHub token: {'set' if os.getenv('GITHUB_TOKEN') else 'not set'} | LLM key: {'set' if any(os.getenv(k) for k in ('LLM_API_KEY','OPENAI_API_KEY')) else 'not set'}")
    print(f"Ollama localhost: {'reachable' if reachable('http://127.0.0.1:11434/api/tags') else 'unreachable'} | Internet: {'reachable' if reachable('https://pypi.org/simple/') else 'unreachable'}")
    print(f"Embedding model: {'cached' if hf_cached else 'not cached'}; download check: {'available' if reachable('https://huggingface.co/api/models/sentence-transformers/all-MiniLM-L6-v2') else 'unavailable'} | numpy installed: {bool(importlib.util.find_spec('numpy'))}")


if __name__ == "__main__":
    main()
