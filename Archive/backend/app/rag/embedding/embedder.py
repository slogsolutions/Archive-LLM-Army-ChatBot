from sentence_transformers import SentenceTransformer
import os

# 🔥 FORCE OFFLINE MODE
os.environ["HF_HUB_OFFLINE"] = "1"

_model = None


def get_model():
    global _model

    if _model is None:
        print("🚀 Loading embedding model (offline)...")

        try:
            _model = SentenceTransformer("BAAI/bge-base-en")

            print("✅ Model loaded from local cache")

        except Exception as e:
            print("❌ MODEL LOAD FAILED:", str(e))
            raise RuntimeError(
                "Embedding model not found locally. "
                "Run once with internet to cache it."
            )

    return _model


def get_embeddings(texts: list[str]):
    model = get_model()

    if not texts:
        return []

    return model.encode(
        texts,
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=False
    ).tolist()