#Elastic Search 

from elasticsearch import Elasticsearch

es = Elasticsearch("http://localhost:9200")



def index_chunk(doc_id, chunk_text, embedding, branch, doc_type, year):
    es.index(
        index="documents",
        body={
            "text": chunk_text,
            "embedding": embedding,
            "document_id": doc_id,
            "branch": branch,
            "document_type": doc_type,
            "year": year
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