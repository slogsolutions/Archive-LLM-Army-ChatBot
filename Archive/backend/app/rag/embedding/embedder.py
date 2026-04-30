from __future__ import annotations
import os
from pathlib import Path
from typing import List

# ---------------------------------------------------------------------------
# Offline mode
# ---------------------------------------------------------------------------
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

_model = None


def get_model():
    global _model

    if _model is None:
        from sentence_transformers import SentenceTransformer
        import torch
        import time

        print("🚀 Loading embedding model…")

        BASE_DIR = Path(__file__).resolve().parents[2]
        model_path = BASE_DIR / "ml_models" / "embedding"

        print(f"📂 Model path : {model_path}")
        print(f"📂 Exists     : {model_path.exists()}")

        if not model_path.exists():
            raise RuntimeError(f"❌ Embedding model not found at: {model_path}")

        from app.rag.hw_config import EMBEDDING_DEVICE
        device = EMBEDDING_DEVICE.lower()

        print(f"📂 Target Device : {device}")

        t0 = time.time()

        # ✅ STEP 1: LOAD WITHOUT DEVICE (CRITICAL FIX)
        _model = SentenceTransformer(str(model_path))

        print("📦 Model loaded on default device")

        # ✅ STEP 2: SAFE DEVICE MOVE (HANDLE META TENSOR ISSUE)
        if device != "cpu":
            try:
                print(f"⚙️ Moving model to {device}...")

                # Move underlying torch model safely
                _model._first_module().auto_model.to(device)

                print(f"✅ Model moved to {device}")

            except Exception as e:
                print(f"⚠️ GPU move failed: {e}")
                print("➡️ Falling back to CPU")

                try:
                    _model._first_module().auto_model.to("cpu")
                except Exception:
                    pass

        print(f"✅ Model ready in {time.time() - t0:.2f}s")

    return _model


def get_embeddings(texts: List[str] | str) -> List[List[float]]:
    from app.rag.embedding.cache import get_cached, set_cached

    print("🧠 get_embeddings called")

    if not texts:
        return []

    if isinstance(texts, str):
        texts = [texts]

    results: List[List[float] | None] = [None] * len(texts)
    uncached_indices: List[int] = []
    uncached_texts: List[str] = []

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
        print(f"🧠 Cache: {cache_hits}/{len(texts)} hit(s)")

    # ── Encode uncached texts ─────────────────────────────────────────────
    if uncached_texts:
        model = get_model()

        print(f"🧠 Encoding {len(uncached_texts)} text(s)…")

        from app.rag.hw_config import EMBEDDING_BATCH

        raw = model.encode(
            uncached_texts,
            batch_size=EMBEDDING_BATCH,
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