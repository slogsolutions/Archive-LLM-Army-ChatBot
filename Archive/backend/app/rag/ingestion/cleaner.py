from __future__ import annotations
import re


def clean_text(text: str) -> str:
    """
    Production-grade OCR cleaner:
    - Fix OCR artifacts
    - Preserve structure (paragraphs, lists)
    - Normalize spacing
    """

    if not text:
        return ""

    # Remove control chars (keep \n)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Fix OCR hyphenation: "secu-\nrity" → "security"
    text = re.sub(r"-\n(\w)", r"\1", text)

    # Fix split ordinal: "1\nST" → "1ST"
    text = re.sub(r'(\d)\s*\n\s*([A-Z]{1,2})', r'\1\2', text)

    # Fix missing spaces: "10THCLASS" → "10TH CLASS"
    text = re.sub(r'([A-Z])([A-Z][a-z])', r'\1 \2', text)

    # Join broken lines inside sentences (but keep paragraph breaks)
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)

    # Normalize spaces
    text = re.sub(r'[ \t]+', ' ', text)

    # Collapse excessive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Strip lines
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    return text.strip()