"""Typed access to the single YAML configuration and environment overrides."""
from functools import lru_cache
from pathlib import Path
import os
import yaml

ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def get_config() -> dict:
    values = yaml.safe_load((ROOT / "config.yaml").read_text())
    values["providers"]["llm_base_url"] = os.getenv("LLM_BASE_URL", values["providers"]["llm_base_url"])
    values["providers"]["llm_model"] = os.getenv("LLM_MODEL", values["providers"]["llm_model"])
    values["mode"] = os.getenv("NOVELTY_MODE", "demo" if os.getenv("NOVELTY_DEMO") == "1" else "full")
    if values["mode"] == "demo":
        values["cache"]["mode"] = "read_only"
    return values
