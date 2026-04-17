from elasticsearch import Elasticsearch

es = Elasticsearch("http://localhost:9200")


def index_document(doc_id, text):
    es.index(
        index="documents",
        id=doc_id,
        body={
            "text": text
        }
    )