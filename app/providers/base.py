"""Vendor-neutral protocols for text generation and embeddings."""
from typing import Protocol


class LLMProvider(Protocol):
    name: str
    model: str
    def generate_json(self, *, system: str, user: str, schema: dict,
                      prompt_id: str, prompt_version: str, temperature: float = 0.0,
                      max_tokens: int = 1500) -> dict: ...
    def generate_text(self, *, system: str, user: str, prompt_id: str,
                      prompt_version: str, temperature: float = 0.0,
                      max_tokens: int = 800) -> str: ...


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dim: int
    def embed(self, texts: list[str], *, kind: str = "passage") -> list[list[float]]: ...
