# main ingestion engine

from app.rag.ingestion.cleaner import clean_text
from app.rag.ingestion.parser import extract_metadata
from app.rag.ingestion.chunker import chunk_text

from app.rag.embedding.embedder import get_embeddings
from app.rag.ingestion.indexer import index_chunk


def ingest_document(doc):

    text = doc.corrected_text or doc.ocr_text

    # 1. CLEAN
    text = clean_text(text)

    # 2. METADATA
    metadata = extract_metadata(doc)

    # 3. CHUNK
    chunks = chunk_text(text)

    print("🔥 TOTAL CHUNKS:", len(chunks))

    if not chunks:
        print("❌ NO CHUNKS CREATED")
        return

    # 🔥 4. EMBEDDINGS (BATCH)
    embeddings = get_embeddings(chunks)

    print("🔥 EMBEDDINGS GENERATED:", len(embeddings))

    # 🔥 5. INDEX
    for chunk, embedding in zip(chunks, embeddings):

        print("➡️ Indexing chunk:", chunk[:60])

        index_chunk(
        doc_id=doc.id,
        chunk=chunk,
        embedding=embedding,
        metadata=metadata
    )