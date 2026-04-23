from sentence_transformers import SentenceTransformer
import os
from pathlib import Path

# 🔥 OFFLINE MODE
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

_model = None


def get_model():

    global _model

    if _model is None:
        print("🚀 Loading embedding model...")

        # ✅ ALWAYS USE PROJECT ROOT (where you run python)
        BASE_DIR = Path.cwd()

        print("📁 Current Working Dir:", BASE_DIR)

        model_path = BASE_DIR / "app" / "ml_models" / "embedding"

        print("📂 Exists:", model_path.exists())
        print("📂 Files:", list(model_path.glob("*")))

        if not model_path.exists():
            raise RuntimeError(f"❌ Model NOT FOUND at: {model_path}")

        import time
        start = time.time()

        _model = SentenceTransformer(str(model_path))

        print(f"✅ Model loaded in {round(time.time() - start, 2)} sec")

    return _model








def get_embeddings(texts):
    print("🧠 get_embeddings called")

    model = get_model()

    print("🧠 Model ready, encoding...")

    if not texts:
        return []

    if isinstance(texts, str):
        texts = [texts]

    embeddings = model.encode(
        texts,
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=True
    )

    print("🧠 Encoding done")

    return embeddings.tolist()