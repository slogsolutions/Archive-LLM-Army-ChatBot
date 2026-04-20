from sentence_transformers import SentenceTransformer
import os

# 🔥 OFFLINE MODE
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

_model = None


def get_model():
    global _model

    if _model is None:
        print("🚀 Loading embedding model...")

        # 🔥 Go from embedder.py → backend/
        base_dir = os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(__file__)   # ← FIXED (4 levels)
                )
            )
        )

        model_path = os.path.join(base_dir, "ml_models", "embedding")

        print(f"📁 Looking for model at: {model_path}")

        if not os.path.exists(model_path):
            raise RuntimeError(f"❌ Model not found at {model_path}")

        _model = SentenceTransformer(model_path)
        print("✅ Model loaded successfully")

    return _model


def get_embeddings(texts: list[str]):
    model = get_model()

    if not texts:
        return []

    if isinstance(texts, str):
        texts = [texts]

    return model.encode(
        texts,
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=False
    ).tolist()