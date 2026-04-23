from __future__ import annotations
import re


# ---------------------------------------------------------------------------
# REGEX — compiled once at import time
# ---------------------------------------------------------------------------

# Detects a line that is a numbered list item: "1. cmd" or "1) cmd" or "1 cmd"
_LIST_LINE_RE = re.compile(r"^\s*\d+[\.\)]\s+\S", re.MULTILINE)

# Detects a bare number line that lost its dot: "1 cmd" (no dot/paren)
_BARE_NUMBER_LINE_RE = re.compile(r"^\s*(\d+)\s+([a-zA-Z\-\.\$\/][^\n]*)$", re.MULTILINE)


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

def clean_text(text: str) -> str:
    """
    Production-grade text cleaner for army RAG ingestion.

    Designed to run AFTER ocr_cleaner.apply_ocr_pipeline() in pipeline.py.
    This function handles general text normalization while deliberately
    PRESERVING numbered list structure so chunker.py can extract ListItems.

    Order of operations matters — do not reorder steps.

    Args:
        text: Raw text from parser (already OCR-cleaned if applicable)

    Returns:
        Cleaned text with list structure intact.
    """
    if not text:
        return ""

    # ------------------------------------------------------------------
    # STEP 1 — Remove non-printable control characters (keep \n and \t)
    # ------------------------------------------------------------------
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # ------------------------------------------------------------------
    # STEP 2 — Fix OCR hyphenation across line breaks
    #   "secu-\nrity"  →  "security"
    #   BUT NOT when the line break is between list items
    # ------------------------------------------------------------------
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    # ------------------------------------------------------------------
    # STEP 3 — Fix split ordinals that OCR breaks across lines
    #   "1\nST"  →  "1ST"
    # ------------------------------------------------------------------
    text = re.sub(r"(\d)\s*\n\s*([A-Z]{1,2})\b", r"\1\2", text)

    # ------------------------------------------------------------------
    # STEP 4 — Fix run-together title-case words (OCR merges)
    #   "10THCLASS"  →  "10TH CLASS"
    # ------------------------------------------------------------------
    text = re.sub(r"([A-Z])([A-Z][a-z])", r"\1 \2", text)

    # ------------------------------------------------------------------
    # STEP 5 — Selectively join broken prose lines
    #
    #   ⚠️  THIS IS THE CRITICAL FIX vs the old cleaner.
    #
    #   Old code did:  re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    #   → This destroyed all list structure by joining every single \n.
    #
    #   New approach: only join a line break if BOTH the line ending
    #   and the next line are clearly prose (not list items, not headings).
    #   We do this line-by-line so we can inspect each transition.
    # ------------------------------------------------------------------
    text = _join_broken_prose_lines(text)

    # ------------------------------------------------------------------
    # STEP 6 — Normalize horizontal whitespace (spaces/tabs → single space)
    # ------------------------------------------------------------------
    text = re.sub(r"[ \t]+", " ", text)

    # ------------------------------------------------------------------
    # STEP 7 — Collapse runs of 3+ blank lines → exactly 2 (one blank line)
    # ------------------------------------------------------------------
    text = re.sub(r"\n{3,}", "\n\n", text)

    # ------------------------------------------------------------------
    # STEP 8 — Strip trailing whitespace from every line
    # ------------------------------------------------------------------
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)

    return text.strip()


# ---------------------------------------------------------------------------
# INTERNAL HELPERS
# ---------------------------------------------------------------------------

def _join_broken_prose_lines(text: str) -> str:
    """
    Join single line-breaks only when both the current line and the next
    line are prose (not list items, not headings, not blank).

    Rules for NOT joining (keep the \n):
      - Either line is empty / blank
      - Either line looks like a list item: starts with digit + dot/paren
      - The next line looks like a heading (short, all-caps or title-case)
      - Current line ends with sentence punctuation (already a full sentence)

    This preserves:
      "1. ls   Directory listing\n2. ls -al  Formatted..."
      "FILE COMMANDS\n1. ls ..."
      "Introduction\n\nThis section..."

    And joins:
      "This is a long sentence that was\nbroken by the OCR scanner."
      → "This is a long sentence that was broken by the OCR scanner."
    """
    lines = text.split("\n")
    result: list[str] = []

    i = 0
    while i < len(lines):
        current = lines[i]

        # If not the last line, decide whether to join with next
        if i < len(lines) - 1:
            nxt = lines[i + 1]

            if _should_join(current, nxt):
                # Merge: append space + next line, skip next iteration
                merged = current.rstrip() + " " + nxt.lstrip()
                result.append(merged)
                i += 2
                continue

        result.append(current)
        i += 1

    return "\n".join(result)


def _should_join(current: str, nxt: str) -> bool:
    """
    Return True only if it is safe to join `current` and `nxt` with a space.
    Conservative — when in doubt, return False (keep the newline).
    """
    c = current.strip()
    n = nxt.strip()

    # Never join if either side is blank
    if not c or not n:
        return False

    # Never join if next line is a list item
    if re.match(r"^\d+[\.\)]\s+\S", n):
        return False

    # Never join if current line is a list item (its description may continue)
    if re.match(r"^\d+[\.\)]\s+\S", c):
        return False

    # Never join if next line looks like a heading
    #   (short, all-caps, or title-case without trailing period)
    if _looks_like_heading(n):
        return False

    # Never join if current line looks like a heading
    if _looks_like_heading(c):
        return False

    # Never join if current line ends with strong sentence punctuation
    # (already complete — next line starts a new sentence)
    if c.endswith((".", "!", "?", ":", ";")):
        return False

    # Never join if next line starts with a capital letter after a
    # sentence-ending punctuation on the current line  (heuristic)
    if c[-1] in ".!?" and n and n[0].isupper():
        return False

    # Safe to join — this looks like a single sentence broken across lines
    return True


def _looks_like_heading(line: str) -> bool:
    """
    Heuristic: short line, all-caps or title-case, no trailing period.
    Matches: "FILE COMMANDS", "Process Management", "SECTION 3"
    """
    line = line.strip()
    if not line or len(line) > 100:
        return False
    words = line.split()
    if len(words) > 10:
        return False
    return (
        line.isupper()
        or (line.istitle() and not line.endswith("."))
    )