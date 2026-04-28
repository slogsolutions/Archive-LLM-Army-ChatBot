"""
Multi-Strategy PDF → Markdown Converter
========================================

Strategy cascade (each is tried in order; first to meet the quality
threshold wins):

  1. Marker   — structure-preserving PDF→MD (pip install marker-pdf)
                Best for digital PDFs with clear layout.
  2. Docling  — IBM document converter (pip install docling)
                Deeper layout analysis, handles complex tables.
  3. PyMuPDF  — font-aware extraction (already installed)
                Uses bold/size flags to detect headings without ML.
  4. PaddleOCR text — already stored in doc.ocr_text
                Plain text fallback for scanned documents.
  5. Future   — VLM (vision-language model) for images / diagrams.

Quality thresholds
------------------
  >= 0.60  → accept immediately
  >= 0.40  → accept if no better option found
  <  0.40  → try next strategy
"""
from __future__ import annotations

import re
import os
import tempfile
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ConversionResult:
    markdown: str
    method:   str           # "marker" | "docling" | "pymupdf" | "paddle_ocr" | "none"
    quality:  float         # 0.0 – 1.0
    is_scanned: bool = False
    has_tables: bool = False
    has_images: bool = False
    warnings:  list[str] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return self.quality >= 0.40 and bool(self.markdown.strip())


# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------

_WATERMARK_RE = re.compile(
    r"^(RESTRICTED|CONFIDENTIAL|SECRET|TOP SECRET|CLASSIFIED)$",
    re.IGNORECASE | re.MULTILINE,
)
_NOISE_CHARS = re.compile(r"[^\w\s\n\t\.\,\;\:\!\?\-\(\)\[\]\#\*\_\>\|\'\"\/\\%@&]")


def score_markdown(md: str) -> float:
    """
    Score 0.0 – 1.0 based on structural richness and noise level.

    Points breakdown
    ----------------
    0.25  ·  Has section headings  (#, ##, ###)
    0.20  ·  Sufficient word count (> 100 words)
    0.10  ·  Word count > 300
    0.15  ·  Has paragraph breaks (\\n\\n)
    0.10  ·  Has lists or bold text (structured content)
    0.20  ·  Low character noise (< 15 % non-printable / garbage)
    """
    if not md or len(md.strip()) < 50:
        return 0.0

    score = 0.0

    # Headings
    if re.search(r"^#{1,4}\s+\w", md, re.MULTILINE):
        score += 0.25

    # Word count
    words = md.split()
    if len(words) > 100:
        score += 0.20
    if len(words) > 300:
        score += 0.10

    # Paragraph structure
    if "\n\n" in md:
        score += 0.15

    # Lists or bold (structured content signals)
    if re.search(r"^[\*\-\d]+[\.]\s", md, re.MULTILINE) or "**" in md:
        score += 0.10

    # Noise ratio
    cleaned = _WATERMARK_RE.sub("", md)
    noise_chars = len(_NOISE_CHARS.findall(cleaned))
    noise_ratio = noise_chars / max(len(cleaned), 1)
    if noise_ratio < 0.05:
        score += 0.20
    elif noise_ratio < 0.15:
        score += 0.10

    return round(min(score, 1.0), 3)


def validate_markdown(result: ConversionResult) -> list[str]:
    """
    Return a list of quality warnings for logging / debugging.
    Does NOT block the result — just informs.
    """
    warnings = []
    md = result.markdown

    if not re.search(r"^#{1,4}\s+\w", md, re.MULTILINE):
        warnings.append("No headings detected — structure may be flat.")

    if len(md.split()) < 50:
        warnings.append("Very short output — possible extraction failure.")

    noise_chars = len(_NOISE_CHARS.findall(md))
    noise_ratio = noise_chars / max(len(md), 1)
    if noise_ratio > 0.20:
        warnings.append(f"High noise ratio ({noise_ratio:.0%}) — garbled OCR likely.")

    tables = md.count("|")
    if tables > 0 and tables < 4:
        warnings.append("Incomplete table detected — may be missing rows.")

    return warnings


# ---------------------------------------------------------------------------
# Strategy 1: Marker
# ---------------------------------------------------------------------------

def try_marker(file_path: str) -> Optional[ConversionResult]:
    """
    Use Marker (pip install marker-pdf) to convert PDF → Markdown.
    Marker runs a layout detection model + OCR for scanned pages.
    Produces structured Markdown with proper headings and tables.
    """
    try:
        # Marker's API changed across versions — handle both
        try:
            from marker.convert import convert_single_pdf
            from marker.models import load_all_models

            models = load_all_models()
            full_text, images, metadata = convert_single_pdf(file_path, models)
        except ImportError:
            # Newer Marker API (>= 0.2)
            from marker.converters.pdf import PdfConverter
            from marker.models import create_model_dict
            from marker.config.parser import ConfigParser

            config  = ConfigParser({})
            models  = create_model_dict()
            conv    = PdfConverter(config=config.generate_config_dict(), artifact_dict=models)
            result  = conv(file_path)
            full_text = result.markdown
            images    = getattr(result, "images", {})

        if not full_text:
            return None

        md = full_text.strip()
        return ConversionResult(
            markdown    = md,
            method      = "marker",
            quality     = score_markdown(md),
            has_images  = bool(images),
        )

    except ImportError:
        print("[MD_PARSER] Marker not installed. Run: pip install marker-pdf")
        return None
    except Exception as e:
        print(f"[MD_PARSER] Marker failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Strategy 2: Docling
# ---------------------------------------------------------------------------

def try_docling(file_path: str) -> Optional[ConversionResult]:
    """
    Use Docling (pip install docling) to convert PDF → Markdown.
    IBM's document converter — excellent for complex layouts and tables.
    """
    try:
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        result    = converter.convert(file_path)
        md        = result.document.export_to_markdown()

        if not md:
            return None

        has_tables = bool(re.search(r"^\|", md, re.MULTILINE))
        return ConversionResult(
            markdown    = md.strip(),
            method      = "docling",
            quality     = score_markdown(md),
            has_tables  = has_tables,
        )

    except ImportError:
        print("[MD_PARSER] Docling not installed. Run: pip install docling")
        return None
    except Exception as e:
        print(f"[MD_PARSER] Docling failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Strategy 3: PyMuPDF font-aware (no extra install needed)
# ---------------------------------------------------------------------------

def try_pymupdf(file_path: str) -> Optional[ConversionResult]:
    """
    Use PyMuPDF's dict mode to extract text with font metadata.
    Detects:
      - Document title (largest font, all-caps on page 0-1)
      - Headings       (bold flag + ≤10 words)
      - Notes          (lines starting with "Note:")
      - Numbered paras (kept as-is, not treated as headings)
    Outputs pseudo-Markdown (# title, ## heading, plain body).
    """
    try:
        import fitz
    except ImportError:
        return None

    WATERMARK = re.compile(
        r"^(RESTRICTED|CONFIDENTIAL|SECRET|TOP SECRET|CLASSIFIED)$",
        re.IGNORECASE,
    )
    NOTE_RE  = re.compile(r"^note\s*[:\-]", re.IGNORECASE)
    PARA_RE  = re.compile(r"^\d+[\.\)]\s")
    SUB_RE   = re.compile(r"^\([a-z]+\)\s", re.IGNORECASE)

    try:
        pdf_doc = fitz.open(file_path)
    except Exception as e:
        print(f"[MD_PARSER] PyMuPDF open failed: {e}")
        return None

    with pdf_doc:
        n = len(pdf_doc)
        if n == 0:
            return None

        # ── Detect document title (largest font on pages 0-1) ─────────────
        title_spans: list[tuple[float, str]] = []
        for pi in range(min(2, n)):
            for blk in pdf_doc[pi].get_text("dict")["blocks"]:
                if blk.get("type") != 0:
                    continue
                for ln in blk["lines"]:
                    for sp in ln["spans"]:
                        t = sp["text"].strip()
                        if t and not WATERMARK.match(t):
                            title_spans.append((sp["size"], t))

        doc_title = ""
        if title_spans:
            max_sz   = max(s for s, _ in title_spans)
            med_sz   = sorted(s for s, _ in title_spans)[len(title_spans) // 2]
            title_parts = [
                t for s, t in title_spans
                if s >= max_sz * 0.85 and (t.isupper() or s > med_sz * 1.1)
            ]
            seen: set[str] = set()
            doc_title = " ".join(
                t for t in title_parts[:8] if t not in seen and not seen.add(t)  # type: ignore
            ).strip()[:240]

        # ── Per-page extraction ───────────────────────────────────────────
        md_lines: list[str] = []
        if doc_title:
            md_lines.append(f"# {doc_title}\n")

        for pi in range(n):
            for blk in pdf_doc[pi].get_text("dict")["blocks"]:
                if blk.get("type") != 0:
                    continue
                for ln in blk["lines"]:
                    txt      = ""
                    is_bold  = False
                    for sp in ln["spans"]:
                        if sp.get("flags", 0) & 16:
                            is_bold = True
                        txt += sp["text"]
                    txt = txt.strip()
                    if not txt or WATERMARK.match(txt):
                        continue

                    words = txt.split()
                    is_heading = (
                        is_bold
                        and 1 <= len(words) <= 10
                        and not PARA_RE.match(txt)
                        and not SUB_RE.match(txt)
                        and txt[-1] not in ".,"
                    )
                    if is_heading:
                        md_lines.append(f"\n## {txt}\n")
                    elif NOTE_RE.match(txt):
                        md_lines.append(f"> **NOTE**: {txt[txt.index(':')+1:].strip()}")
                    else:
                        md_lines.append(txt)

        md = "\n".join(md_lines).strip()
        if not md:
            return None

        return ConversionResult(
            markdown = md,
            method   = "pymupdf",
            quality  = score_markdown(md),
        )


# ---------------------------------------------------------------------------
# Strategy 4: PaddleOCR fallback (text already stored)
# ---------------------------------------------------------------------------

def from_ocr_text(ocr_text: str) -> ConversionResult:
    """
    Wrap already-extracted PaddleOCR text in a ConversionResult.
    Tries to infer headings from short ALL-CAPS lines.
    """
    if not ocr_text or not ocr_text.strip():
        return ConversionResult(markdown="", method="none", quality=0.0)

    lines     = ocr_text.splitlines()
    md_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            md_lines.append("")
            continue
        words = stripped.split()
        # Heuristic: short ALL-CAPS line with no trailing period = section heading
        if (
            stripped.isupper()
            and 1 <= len(words) <= 8
            and not stripped.endswith(".")
        ):
            md_lines.append(f"\n## {stripped}\n")
        else:
            md_lines.append(stripped)

    md = "\n".join(md_lines).strip()
    return ConversionResult(
        markdown    = md,
        method      = "paddle_ocr",
        quality     = score_markdown(md),
        is_scanned  = True,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

QUALITY_ACCEPT  = 0.60   # accept immediately above this threshold
QUALITY_MINIMUM = 0.40   # accept if nothing better is available


def convert_to_markdown(
    file_path: Optional[str],
    ocr_text:  Optional[str] = None,
) -> ConversionResult:
    """
    Convert a document to Markdown using the best available strategy.

    Parameters
    ----------
    file_path : path to the local PDF (or None if not available)
    ocr_text  : already-extracted OCR text (PaddleOCR output), used as fallback

    Returns
    -------
    ConversionResult with .markdown, .method, .quality
    """
    best: Optional[ConversionResult] = None

    def _try(result: Optional[ConversionResult], label: str):
        nonlocal best
        if result is None:
            return
        w = validate_markdown(result)
        result.warnings = w
        if w:
            print(f"[MD_PARSER] {label} warnings: {'; '.join(w)}")
        print(f"[MD_PARSER] {label}: quality={result.quality:.2f}")
        if result.quality >= QUALITY_ACCEPT:
            return result              # caller handles the early-return
        if best is None or result.quality > best.quality:
            best = result
        return None

    if file_path and os.path.isfile(file_path):
        # ── Strategy 1: Marker ───────────────────────────────────────────
        print("[MD_PARSER] Trying Marker…")
        r = try_marker(file_path)
        if _try(r, "Marker") is not None:
            return r

        # ── Strategy 2: Docling ──────────────────────────────────────────
        print("[MD_PARSER] Trying Docling…")
        r = try_docling(file_path)
        if _try(r, "Docling") is not None:
            return r

        # ── Strategy 3: PyMuPDF (always available) ───────────────────────
        print("[MD_PARSER] Trying PyMuPDF font-aware…")
        r = try_pymupdf(file_path)
        if _try(r, "PyMuPDF") is not None:
            return r

    # ── Strategy 4: PaddleOCR text fallback ─────────────────────────────
    if ocr_text:
        print("[MD_PARSER] Using PaddleOCR stored text…")
        r = from_ocr_text(ocr_text)
        _try(r, "PaddleOCR")

    if best and best.quality >= QUALITY_MINIMUM:
        print(f"[MD_PARSER] Using best result: {best.method} (quality={best.quality:.2f})")
        return best

    print("[MD_PARSER] All strategies failed or quality too low — returning empty.")
    return ConversionResult(markdown="", method="none", quality=0.0)


# ---------------------------------------------------------------------------
# Markdown → ParsedDocument helper (used by parser.py)
# ---------------------------------------------------------------------------

def markdown_to_sections(
    md: str,
) -> list[tuple[str, str, str]]:
    """
    Parse markdown into a list of (title, heading, body) triples.

    - Lines starting with `# ` → document title (first occurrence only)
    - Lines starting with `## ` or `### ` → section heading
    - Everything else → body text for the current section

    Returns list of (doc_title, section_heading, body_text).
    One entry per section.  The first section may have an empty heading
    (content before the first `##`).
    """
    doc_title    = ""
    cur_heading  = ""
    cur_body:  list[str] = []
    sections:  list[tuple[str, str, str]] = []

    for raw_line in md.splitlines():
        line = raw_line.rstrip()

        if line.startswith("# ") and not doc_title:
            doc_title = line[2:].strip()
            continue

        if line.startswith("## ") or line.startswith("### "):
            # Flush current section
            body = "\n".join(cur_body).strip()
            if body or cur_heading:
                sections.append((doc_title, cur_heading, body))
            cur_heading = line.lstrip("#").strip()
            cur_body    = []
            continue

        # Skip horizontal rules
        if re.match(r"^[-_\*]{3,}$", line):
            continue

        cur_body.append(line)

    # Flush last section
    body = "\n".join(cur_body).strip()
    if body or cur_heading:
        sections.append((doc_title, cur_heading, body))

    return sections
