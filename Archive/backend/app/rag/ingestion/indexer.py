# 04 send to Elasticsearch

from elasticsearch import Elasticsearch

es = Elasticsearch("http://localhost:9200")


def index_chunk(doc_id, chunk, embedding, metadata):
    es.index(
        index="documents",
        body={
            "text": chunk,
            "embedding": embedding,
            "document_id": doc_id,
            **metadata
        }
    )