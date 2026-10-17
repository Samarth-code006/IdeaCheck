"""No-download TF-IDF vector provider used when neural models are unavailable."""
from app.retrieval.dense import vectorize


class TfidfEmbedder:
    name="tfidf"
    model="builtin-tfidf-v1"
    dim=0
    def embed(self,texts:list[str],*,kind:str="passage")->list[list[float]]:
        vectors,vocab=vectorize(texts)
        self.dim=len(vocab)
        return [[vector.get(token,0.0) for token in vocab] for vector in vectors]
