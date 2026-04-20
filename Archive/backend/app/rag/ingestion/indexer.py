import os
from elasticsearch import Elasticsearch
from dotenv import load_dotenv
from pathlib import Path

# ✅ Load .env (from incoming branch)
load_dotenv(
    dotenv_path=Path(__file__).resolve().parent.parent.parent.parent / ".env"
)

# ✅ Use env-based ES URL (fallback to localhost)
es = Elasticsearch(os.getenv("ES_URL", "http://localhost:9200"))


def index_chunk(doc_id, chunk, embedding, metadata):
    try:
        data = {
            "doc_id": doc_id,
            "content": chunk,
            "embedding": embedding,

            # 🔥 FLATTEN IMPORTANT FIELDS (keep this!)
            "branch": metadata.get("branch"),
            "doc_type": metadata.get("doc_type"),
            "year": metadata.get("year"),
            "section": metadata.get("section"),

            # full metadata
            "metadata": metadata
        }

        # 🔥 DEBUG
        print("➡️ Indexing chunk:", chunk[:50])

        res = es.index(
            index="documents",
            document=data,   # ✅ correct (NOT body)
            refresh=True
        )

        print("✅ INDEXED:", res["_id"])

    except Exception as e:
        print("❌ ES ERROR:", str(e))