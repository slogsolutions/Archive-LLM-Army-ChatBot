def chunk_text(text, size=400, overlap=50):
    paragraphs = text.split("\n")

    chunks = []
    current_chunk = []

    for para in paragraphs:
        words = para.split()

        if len(current_chunk) + len(words) <= size:
            current_chunk.extend(words)
        else:
            chunks.append(" ".join(current_chunk))
            current_chunk = words

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks