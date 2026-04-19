# rag/ingestion/
```
cleaner.py     → clean OCR text
parser.py      → extract metadata
chunker.py     → split text
indexer.py     → send to Elasticsearch
```

# rag/embedding/
```
embedder.py    → BGE embedding model
```

# rag/vector_store/
```
elastic_store.py → (optional abstraction layer)
```


# rag/retriever/
```
retriever.py   → hybrid search (BM25 + vector)
query_parser.py → (later: advanced queries)
reranker.py     → (later phase)
```


# rag/pipeline.py
```
main ingestion engine
```


# FINAL FLOW (AFTER WORKER)

```
1. Upload API
   ↓
2. MinIO (store file)
   ↓
3. DB (metadata)
   ↓
4. Worker triggered
   ↓
5. OCR (PaddleOCR)
   ↓
6. SAVE OCR TEXT (DB)
   ↓
7.  CALL RAG PIPELINE
       ↓
       cleaner
       ↓
       parser (metadata)
       ↓
       chunker
       ↓
       embedder
       ↓
       indexer (Elasticsearch)
   ↓
8. status = indexed

```