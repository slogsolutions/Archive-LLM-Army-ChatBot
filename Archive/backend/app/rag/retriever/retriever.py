# 07 hybrid search (BM25 + vector)from elasticsearch import Elasticsearch

es = Elasticsearch("http://localhost:9200")


def search(query, embedding):

    return es.search(
        index="documents",
        body={
            "query": {
                "bool": {
                    "should": [
                        {"match": {"text": query}},  # BM25
                        {
                            "knn": {
                                "embedding": {
                                    "vector": embedding,
                                    "k": 5
                                }
                            }
                        }
                    ]
                }
            }
        }
    )