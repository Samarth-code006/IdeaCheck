"""Optional local sentence-transformers adapter; downloads only when selected."""
import importlib.util
from app.config import get_config


class LocalSentenceEmbedder:
    name="sentence-transformers"
    def __init__(self,model_name:str|None=None):
        if importlib.util.find_spec("sentence_transformers") is None:
            raise RuntimeError("sentence-transformers is not installed; use the TF-IDF fallback or install the optional local-model extra.")
        from sentence_transformers import SentenceTransformer
        self.model=model_name or get_config()["providers"]["embed_model"]
        self.encoder=SentenceTransformer(self.model)
        self.dim=self.encoder.get_sentence_embedding_dimension()

    def embed(self,texts:list[str],*,kind:str="passage"):
        if kind not in ("query","passage"):
            raise ValueError("kind must be query or passage")
        # MiniLM has no asymmetric query prefix; `kind` keeps the provider API swappable.
        return self.encoder.encode(texts,normalize_embeddings=True,convert_to_numpy=True).tolist()
