from __future__ import annotations
import re
from dataclasses import dataclass
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from app.rag.ingestion.parser import ParsedPage


# =========================
# REGEX
# =========================

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
LIST_SPLIT = re.compile(r"\n?\d+[\.\)]\s+")


# =========================
# DATA CLASS
# =========================

@dataclass
class Chunk:
    text: str
    page_number: int
    chunk_index: int
    total_chunks: int = 0
    heading: str = ""
    char_offset: int = 0


# =========================
# HELPERS
# =========================

def _split_sentences(text: str) -> List[str]:
    parts = _SENT_SPLIT.split(text)
    return [p.strip() for p in parts if p.strip()]


def _split_structured(text: str) -> List[str]:
    """
    Handle numbered lists like:
    1. ...
    2. ...
    """
    parts = LIST_SPLIT.split(text)

    return [p.strip() for p in parts if p.strip()]


def _is_heading(line: str) -> bool:
    line = line.strip()

    if not line or len(line) > 120:
        return False

    words = line.split()

    if len(words) > 12:
        return False

    return (
        line.isupper()
        or (line.istitle() and not line.endswith("."))
        or (re.match(r"^\d+[\.\)]\s+\w", line) and len(words) <= 8)
    )


# =========================
# MAIN FUNCTION
# =========================

def chunk_document(
    pages: List["ParsedPage"],
    chunk_size: int = 350,
    overlap: int = 80,
) -> List[Chunk]:

    sent_meta: List[tuple[str, int, str]] = []
    current_heading = ""

    # =========================
    # STEP 1: STRUCTURE AWARE FLATTEN
    # =========================
    for page in pages:
        text = page.text

        if not text.strip():
            continue

        if page.heading:
            current_heading = page.heading

        paragraphs = re.split(r"\n{2,}", text)

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Detect heading
            first_line = para.split("\n")[0].strip()
            if _is_heading(first_line):
                current_heading = first_line

            # 🔥 FIRST split structured lists
            blocks = _split_structured(para)

            for block in blocks:

                # THEN split sentences
                sentences = _split_sentences(block)

                if not sentences:
                    sentences = [block]

                for s in sentences:
                    if s.strip():
                        sent_meta.append((s.strip(), page.page_number, current_heading))

    if not sent_meta:
        return []

    # =========================
    # STEP 2: SLIDING WINDOW
    # =========================
    chunks: List[Chunk] = []
    n = len(sent_meta)
    i = 0

    while i < n:

        word_count = 0
        j = i

        while j < n and word_count < chunk_size:
            word_count += len(sent_meta[j][0].split())
            j += 1

        chunk_sents = sent_meta[i:j]

        chunk_text = " ".join(s[0] for s in chunk_sents)
        page_num = chunk_sents[0][1]
        heading = chunk_sents[0][2]

        char_offset = sum(len(s[0]) + 1 for s in sent_meta[:i])

        chunks.append(Chunk(
            text=chunk_text,
            page_number=page_num,
            chunk_index=len(chunks),
            heading=heading,
            char_offset=char_offset,
        ))

        # =========================
        # OVERLAP LOGIC
        # =========================
        skip_words = max(chunk_size - overlap, 1)
        skipped = 0
        skip_i = i

        while skip_i < j and skipped < skip_words:
            skipped += len(sent_meta[skip_i][0].split())
            skip_i += 1

        i = max(skip_i, i + 1)

    # =========================
    # STEP 3: FINALIZE
    # =========================
    total = len(chunks)
    for c in chunks:
        c.total_chunks = total

    return chunks