import os
from elasticsearch import Elasticsearch
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent.parent / ".env")

es = Elasticsearch(os.getenv("ES_URL", "http://localhost:9200"))


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