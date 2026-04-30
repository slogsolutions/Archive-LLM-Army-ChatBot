from __future__ import annotations
"""
Cross-encoder reranker — Stage 5b of the RAG pipeline.

A cross-encoder reads (query, document) TOGETHER through full self-attention,
giving dramatically more accurate relevance scores than bi-encoder cosine
similarity.  It runs as a post-retrieval re-scorer on the top-K candidates
returned by hybrid BM25+KNN search.

Model: cross-encoder/ms-marco-MiniLM-L-6-v2
  Size   : ~85 MB
  Speed  : ~50-200 ms for 10 pairs on CPU
  Source : https://huggingface.co/cross-encoder/ms-marco-MiniLM-L-6-v2
  Download: python scripts/download_models.py

Falls back silently to original ES scores if model is not found.
"""
import os
import time
from pathlib import Path
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from app.rag.retriever.retriever import SearchResult

os.environ["HF_HUB_OFFLINE"]      = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

MODEL_PATH = Path(__file__).resolve().parents[2] / "ml_models" / "reranker"

_model = None
_model_available: bool | None = None   # None = not yet checked


def _get_model():
    global _model, _model_available

    if _model_available is False:
        return None

    if _model is not None:
        return _model

    if not MODEL_PATH.exists() or not any(MODEL_PATH.iterdir()):
        print(f"[CROSS-ENCODER] Model not found at {MODEL_PATH}")
        print("[CROSS-ENCODER] Run: python scripts/download_models.py")
        _model_available = False
        return None

    try:
        from sentence_transformers import CrossEncoder
        from app.rag.hw_config import RERANKER_DEVICE
        t0 = time.time()
        print(f"[CROSS-ENCODER] Loading from {MODEL_PATH}  device={RERANKER_DEVICE.upper()}…")
        _model = CrossEncoder(str(MODEL_PATH), max_length=512, device=RERANKER_DEVICE)
        _model_available = True
        print(f"[CROSS-ENCODER] Ready in {time.time() - t0:.2f}s")
        return _model
    except Exception as e:
        print(f"[CROSS-ENCODER] Load failed: {e}")
        _model_available = False
        return None


def rerank(
    query: str,
    results: List["SearchResult"],
) -> List["SearchResult"]:
    """
    Re-score `results` using the cross-encoder and return them sorted by
    descending cross-encoder score.

    For list items (commands), the query is paired with
    "{command} — {description}" to give the cross-encoder richer signal.

    Returns the original results in original order if the model is unavailable.
    """
    if not results:
        return results

    model = _get_model()
    if model is None:
        return results

    # Build (query, passage) pairs
    pairs: list[tuple[str, str]] = []
    for r in results:
        if r.is_list_item and r.command:
            doc_text = f"{r.command} — {r.description or r.content}"
        else:
            doc_text = r.content
        pairs.append((query, doc_text[:512]))

    try:
        scores = model.predict(pairs, show_progress_bar=False)
        for r, score in zip(results, scores):
            r.score = float(score)
        results.sort(key=lambda x: x.score, reverse=True)
        print(f"[CROSS-ENCODER] Rescored {len(results)} results")
    except Exception as e:
        print(f"[CROSS-ENCODER] Predict error: {e} — keeping original order")

    return results


def is_available() -> bool:
    """Return True if the cross-encoder model is loaded and ready."""
    return _model_available is True or _get_model() is not None
