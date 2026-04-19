from elasticsearch import Elasticsearch

es = Elasticsearch("http://localhost:9200")


def index_chunk(doc_id, chunk, embedding, metadata):
    try:
        data = {
         "doc_id": doc_id,
         "content": chunk,
         "embedding": embedding,

    # 🔥 FLATTEN IMPORTANT FIELDS
         "branch": metadata.get("branch"),
         "doc_type": metadata.get("doc_type"),
         "year": metadata.get("year"),
         "section": metadata.get("section"),

    # keep full metadata
         "metadata": metadata
}

        # 🔥 DEBUG
        print("➡️ Indexing chunk:", chunk[:50])

        res = es.index(
            index="documents",   # ⚠️ keep SAME everywhere
            document=data,
            refresh=True
        )

        print("✅ INDEXED:", res["_id"])

    except Exception as e:
        print("❌ ES ERROR:", str(e))