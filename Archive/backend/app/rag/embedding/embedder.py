from __future__ import annotations
import os
from pathlib import Path
from typing import List

# ---------------------------------------------------------------------------
# Offline mode — model must be pre-downloaded to app/ml_models/embedding/
# ---------------------------------------------------------------------------
os.environ["HF_HUB_OFFLINE"]       = "1"
os.environ["TRANSFORMERS_OFFLINE"]  = "1"

_model = None


def get_model():
    global _model

    if _model is None:
        from sentence_transformers import SentenceTransformer

        print("🚀 Loading embedding model…")

        BASE_DIR = Path(__file__).resolve().parents[2]   # app/
        model_path = BASE_DIR / "ml_models" / "embedding"

        # Always resolve from the project root (where you run `python`)
        # model_path = Path.cwd() / "app" / "ml_models" / "embedding"

        print(f"📂 Model path : {model_path}")
        print(f"📂 Exists     : {model_path.exists()}")

        if not model_path.exists():
            raise RuntimeError(f"❌ Embedding model not found at: {model_path}")

        import time
        t0 = time.time()
        _model = SentenceTransformer(str(model_path))
        print(f"✅ Model loaded in {time.time() - t0:.2f}s")

    return _model


def get_embeddings(texts: List[str] | str) -> List[List[float]]:
    """
    Encode a list of strings and return their 768-dim embeddings.
    Results are cached in Redis (2-hour TTL) to avoid re-encoding the
    same query text on every request — significant win on CPU inference.
    """
    from app.rag.embedding.cache import get_cached, set_cached

    print("🧠 get_embeddings called")

    if not texts:
        return []

    if isinstance(texts, str):
        texts = [texts]

    results: List[List[float] | None] = [None] * len(texts)
    uncached_indices: List[int] = []
    uncached_texts:   List[str] = []

    # ── Cache lookup ──────────────────────────────────────────────────────
    for i, text in enumerate(texts):
        hit = get_cached(text)
        if hit is not None:
            results[i] = hit
        else:
            uncached_indices.append(i)
            uncached_texts.append(text)

    cache_hits = len(texts) - len(uncached_texts)
    if cache_hits:
        print(f"🧠 Cache: {cache_hits}/{len(texts)} hit(s) — skipping model for those")

    # ── Encode uncached texts ─────────────────────────────────────────────
    if uncached_texts:
        model = get_model()
        print(f"🧠 Encoding {len(uncached_texts)} text(s)…")
        raw = model.encode(
            uncached_texts,
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=len(uncached_texts) > 10,
        )
        for idx, (orig_i, text) in enumerate(zip(uncached_indices, uncached_texts)):
            vec = raw[idx].tolist()
            results[orig_i] = vec
            set_cached(text, vec)
        print("🧠 Encoding done")

    final = [r for r in results if r is not None]
    if final and len(final[0]) != 768:
        raise ValueError("❌ Embedding dimension mismatch")

    return final