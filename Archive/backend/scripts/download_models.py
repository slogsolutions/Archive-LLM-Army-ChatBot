"""
Download all offline models for the Army Archive RAG system.

Run ONCE from the Archive/backend/ directory (requires internet):
    cd Archive/backend
    python scripts/download_models.py

Downloads:
    cross-encoder/ms-marco-MiniLM-L-6-v2  (~85 MB)
        → app/ml_models/reranker/

The embedding model (app/ml_models/embedding/) is assumed already present.
After this script completes, the server runs 100% offline.
"""
import sys
from pathlib import Path

# Run from Archive/backend/ so this path resolves correctly
ML_MODELS_DIR = Path(__file__).resolve().parent.parent / "app" / "ml_models"
ML_MODELS_DIR.mkdir(parents=True, exist_ok=True)


def download_reranker() -> bool:
    reranker_path = ML_MODELS_DIR / "reranker"

    if reranker_path.exists() and any(reranker_path.iterdir()):
        print(f"✅ Reranker already at {reranker_path} — skipping download")
        return True

    print("📥 Downloading cross-encoder/ms-marco-MiniLM-L-6-v2 (~85 MB)…")
    print("   This is a cross-encoder that dramatically improves reranking quality.")
    try:
        from sentence_transformers import CrossEncoder
        model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=512)
        model.save(str(reranker_path))
        print(f"✅ Saved to {reranker_path}")
        return True
    except Exception as e:
        print(f"❌ Download failed: {e}")
        print("   Make sure sentence-transformers is installed:")
        print("   pip install sentence-transformers")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Army Archive — Offline Model Downloader")
    print("=" * 60)

    ok = download_reranker()

    if ok:
        print("\n✅ All models downloaded. The system is now fully offline.")
        print("   Restart uvicorn — the cross-encoder loads automatically.")
    else:
        sys.exit(1)
