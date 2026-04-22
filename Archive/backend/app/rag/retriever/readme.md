# Final Retriver Structure 

```
app/rag/retriever/
│
├── query_parser.py      # understand user query
├── rbac_filter.py       # convert user → ES filters
├── retriever.py         # main search logic (hybrid)
├── formatter.py         # clean output for API
└── reranker.py          # (optional Phase 2)

```

# RETRIEVAL FLOW

```
User Query
   ↓
query_parser
   ↓
embed_query
   ↓
rbac_filter (user → filters)
   ↓
Elasticsearch (hybrid_search)
   ↓
formatter
   ↓
API response
```