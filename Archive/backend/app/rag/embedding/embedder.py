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
    Encode a list of strings and return their embeddings.

    Returns
    -------
    List[List[float]]  — shape (len(texts), 768)

    FIX applied here
    ----------------
    Old code had a trailing comma on the return statement:
        return embeddings.tolist(),          ← WRONG — returns a tuple (list,)
    This made len(embeddings[0]) == 1 instead of 768,
    causing the dimension check in pipeline.py to always fail.
    """
    print("🧠 get_embeddings called")

    if not texts:
        return []

    if isinstance(texts, str):
        texts = [texts]

    model = get_model()

    print(f"🧠 Encoding {len(texts)} text(s)…")

    embeddings = model.encode(
        texts,
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=len(texts) > 10,   # only show bar for large batches
    )

    if len(embeddings[0]) != 768:
        raise ValueError("❌ Embedding dimension mismatch")

    print("🧠 Encoding done")

    # ⚠️  NO trailing comma — returns List[List[float]], not a tuple
    return embeddings.tolist()