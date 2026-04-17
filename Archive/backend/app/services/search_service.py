from elasticsearch import Elasticsearch

es = Elasticsearch("http://localhost:9200")


def index_document(doc_id, text):
    es.index(
        index="documents",
        id=doc_id,
        body={
            "content": text
        }
    )


def search_documents(query: str):
    res = es.search(
        index="documents",
        body={
            "query": {
                "match": {
                    "content": query
                }
            }
        }
    )
    return res["hits"]["hits"]