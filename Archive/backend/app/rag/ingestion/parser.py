from __future__ import annotations
import os
import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class ParsedPage:
    page_number: int
    text: str
    heading: str = ""


@dataclass
class ParsedDocument:
    pages: List[ParsedPage]
    file_type: str = ""

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text.strip())

    @property
    def total_pages(self) -> int:
        return len(self.pages)


def extract_metadata(doc) -> dict:
    return {
        "branch": doc.branch_name or "",
        "doc_type": doc.document_type_name or "",
        "year": doc.year,
        "section": doc.section or "",
        "hq_id": doc.hq_id,
        "unit_id": doc.unit_id,
        "branch_id": doc.branch_id,
        "uploaded_by": doc.uploaded_by,
        "file_name": doc.file_name,
        "file_type": doc.file_type or "",
        "min_visible_rank": doc.min_visible_rank if doc.min_visible_rank is not None else 6,
    }


def parse_document(file_path: str, ocr_text: str = None) -> ParsedDocument:
    """Parse any supported document format into structured pages."""
    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext == ".pdf":
            return _parse_pdf(file_path, ocr_text)
        elif ext in (".docx", ".doc"):
            return _parse_docx(file_path)
        elif ext in (".xlsx", ".xls"):
            return _parse_xlsx(file_path)
        elif ext == ".csv":
            return _parse_csv(file_path)
        elif ext in (".pptx", ".ppt"):
            return _parse_pptx(file_path)
        elif ext in (".txt", ".text", ".md"):
            return _parse_txt(file_path)
        elif ext in (".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"):
            return _parse_image(file_path, ocr_text)
        else:
            # Attempt plain text fallback
            return _parse_txt(file_path)
    except Exception as e:
        print(f"[PARSER] Error parsing {ext}: {e}")
        return ParsedDocument(pages=[], file_type=ext.lstrip("."))


def _parse_pdf(file_path: str, ocr_text: str = None) -> ParsedDocument:
    """
    Extract text from PDF using PyMuPDF direct extraction first.
    Falls back to provided ocr_text if pages are empty (scanned docs).
    """
    import fitz

    pages = []
    with fitz.open(file_path) as pdf:
        for i, page in enumerate(pdf):
            text = page.get_text("text").strip()
            pages.append(ParsedPage(page_number=i + 1, text=text))

    total_digital_chars = sum(len(p.text) for p in pages)

    # If digital extraction was sparse, prefer OCR text
    if total_digital_chars < 50 * len(pages) and ocr_text:
        # OCR text has pages separated by double-newline
        ocr_page_texts = [t.strip() for t in ocr_text.split("\n\n") if t.strip()]
        pages = [
            ParsedPage(page_number=i + 1, text=t)
            for i, t in enumerate(ocr_page_texts)
        ]

    return ParsedDocument(pages=[p for p in pages if p.text.strip()], file_type="pdf")


def _parse_docx(file_path: str) -> ParsedDocument:
    from docx import Document as DocxDoc

    doc = DocxDoc(file_path)
    pages: List[ParsedPage] = []
    current_lines: List[str] = []
    current_heading = ""
    page_num = 1

    for para in doc.paragraphs:
        style = para.style.name.lower() if para.style else ""
        text = para.text.strip()
        if not text:
            continue

        if "heading" in style or re.match(r'^(chapter|section|part)\b', text, re.IGNORECASE):
            # Flush current section as a page
            if current_lines:
                pages.append(ParsedPage(
                    page_number=page_num,
                    text="\n".join(current_lines),
                    heading=current_heading,
                ))
                page_num += 1
                current_lines = []
            current_heading = text
            current_lines.append(text)
        else:
            current_lines.append(text)

    # Tables
    for table in doc.tables:
        rows = []
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                rows.append(" | ".join(cells))
        if rows:
            current_lines.append("\n".join(rows))

    if current_lines:
        pages.append(ParsedPage(
            page_number=page_num,
            text="\n".join(current_lines),
            heading=current_heading,
        ))

    return ParsedDocument(pages=pages, file_type="docx")


def _parse_xlsx(file_path: str) -> ParsedDocument:
    import openpyxl

    wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    pages: List[ParsedPage] = []

    for idx, sheet in enumerate(wb.worksheets):
        rows = []
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c) if c is not None else "" for c in row]
            if any(c.strip() for c in cells):
                rows.append(" | ".join(cells))
        if rows:
            pages.append(ParsedPage(
                page_number=idx + 1,
                text="\n".join(rows),
                heading=sheet.title or f"Sheet {idx + 1}",
            ))

    wb.close()
    return ParsedDocument(pages=pages, file_type="xlsx")


def _parse_csv(file_path: str) -> ParsedDocument:
    import csv

    rows: List[str] = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            for row in reader:
                if any(c.strip() for c in row):
                    rows.append(" | ".join(row))
    except Exception as e:
        print(f"[PARSER] CSV error: {e}")

    return ParsedDocument(
        pages=[ParsedPage(page_number=1, text="\n".join(rows))],
        file_type="csv",
    )


def _parse_pptx(file_path: str) -> ParsedDocument:
    from pptx import Presentation

    prs = Presentation(file_path)
    pages: List[ParsedPage] = []

    for i, slide in enumerate(prs.slides):
        texts: List[str] = []
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                t = para.text.strip()
                if t:
                    texts.append(t)
        if texts:
            heading = texts[0] if len(texts[0]) < 100 else ""
            pages.append(ParsedPage(
                page_number=i + 1,
                text="\n".join(texts),
                heading=heading,
            ))

    return ParsedDocument(pages=pages, file_type="pptx")


def _parse_txt(file_path: str) -> ParsedDocument:
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception as e:
        print(f"[PARSER] TXT error: {e}")
        return ParsedDocument(pages=[], file_type="txt")

    if len(text) <= 4000:
        return ParsedDocument(
            pages=[ParsedPage(page_number=1, text=text)],
            file_type="txt",
        )

    # Group paragraphs into logical pages (~2000 chars each)
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    pages: List[ParsedPage] = []
    current: List[str] = []
    current_len = 0
    page_num = 1

    for para in paragraphs:
        current.append(para)
        current_len += len(para)
        if current_len >= 2000:
            pages.append(ParsedPage(page_number=page_num, text="\n\n".join(current)))
            page_num += 1
            current = []
            current_len = 0

    if current:
        pages.append(ParsedPage(page_number=page_num, text="\n\n".join(current)))

    return ParsedDocument(pages=pages, file_type="txt")


def _parse_image(file_path: str, ocr_text: str = None) -> ParsedDocument:
    if ocr_text:
        return ParsedDocument(
            pages=[ParsedPage(page_number=1, text=ocr_text)],
            file_type="image",
        )
    return ParsedDocument(pages=[], file_type="image")
