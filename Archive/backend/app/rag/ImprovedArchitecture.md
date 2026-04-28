```
app/
  rag/
    ingestion/
      cleaner.py       ← FIXED  (was breaking list structure)
      chunker.py       ← FIXED  (ListItem now has .text, .page_number etc.)
      ocr_cleaner.py   ← unchanged (already correct)
      parser.py        ← unchanged
      indexer.py       ← unchanged
    embedding/
      embedder.py      ← FIXED  (trailing comma bug removed)
    vector_store/
      elastic_store.py ← unchanged
    retriever/
      retriever.py     ← unchanged
      query_parser.py  ← unchanged
      reranker.py      ← unchanged
      formatter.py     ← unchanged
    llm/               ← NEW folder
      __init__.py      ← (empty file, create it)
      llm_client.py    ← NEW
      context_builder.py ← NEW
      prompt_builder.py  ← NEW
      qa_pipeline.py     ← NEW (the main entry point for query)
  api/
    chat.py            ← NEW
  pipeline.py          ← FIXED (calls ocr_cleaner first, handles ListItem everywhere)

test_qa.py             ← NEW (run this to verify end-to-end)
```