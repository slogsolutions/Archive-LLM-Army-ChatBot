# main ingestion engine

from app.rag.ingestion.cleaner import clean_text
from app.rag.ingestion.parser import extract_metadata
from app.rag.ingestion.chunker import chunk_text

from app.rag.embedding.embedder  import get_embedding
from app.rag.ingestion.indexer import index_chunk


def ingest_document(doc):

    text = doc.corrected_text or doc.ocr_text

    # 1. CLEAN
    text = clean_text(text)

    # 2. METADATA
    metadata = extract_metadata(doc)

    # 3. CHUNK
    chunks = chunk_text(text)

    for chunk in chunks:
        embedding = get_embedding(chunk)

        index_chunk(
            doc_id=doc.id,
            chunk=chunk,
            embedding=embedding,
            metadata=metadata
        )