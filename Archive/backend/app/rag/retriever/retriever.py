import os
from elasticsearch import Elasticsearch
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent.parent / ".env")

es = Elasticsearch(os.getenv("ES_URL", "http://localhost:9200"))


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