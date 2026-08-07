"""Thin wrapper around sentence-transformers so the model is loaded once and reused."""
import numpy as np

_MODEL = None
MODEL_NAME = "all-MiniLM-L6-v2"  # small (80MB), fast on CPU, good enough for abstract-level similarity


def _get_model():
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer(MODEL_NAME)
    return _MODEL


def embed_texts(texts: list[str]) -> np.ndarray:
    model = _get_model()
    return np.array(model.encode(texts, show_progress_bar=False, normalize_embeddings=True))


def paper_text(paper: dict) -> str:
    return f"{paper.get('title', '')}. {paper.get('abstract', '')}"


def cosine_sim(vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    # both assumed already normalized
    return matrix @ vec
