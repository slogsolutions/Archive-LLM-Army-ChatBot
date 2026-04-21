from __future__ import annotations
import re


def clean_text(text: str) -> str:
    """
    Normalize OCR/parsed text while preserving paragraph structure.

    - Removes null bytes and ASCII control chars (keeps \\n and \\t)
    - Fixes OCR hyphenation artifacts (word split across lines)
    - Collapses multiple spaces/tabs to a single space per line
    - Strips trailing/leading whitespace per line
    - Reduces 3+ consecutive newlines to 2 (paragraph boundary preserved)
    """
    if not text:
        return ""

    # Remove null bytes and control chars except newline (0x0a) and tab (0x09)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Fix OCR hyphenation: "secu-\nrity" → "security"
    text = re.sub(r"-\n(\w)", r"\1", text)

    # Collapse multiple spaces/tabs within a line
    text = re.sub(r"[ \t]+", " ", text)

    # Strip each line
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    # Collapse 3+ blank lines to 2 (keep paragraph boundaries)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()
