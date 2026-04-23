from __future__ import annotations
import gc
import cv2
import numpy as np
import fitz  # PyMuPDF


def _get_ocr():
    """Lazy-initialise PaddleOCR (CPU-only, offline safe)."""
    from paddleocr import PaddleOCR
    return PaddleOCR(
        use_gpu=False,
        use_angle_cls=True,
        lang="en",
        rec_batch_num=2,
        cpu_threads=4,
    )


def _preprocess(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    if max(h, w) > 1200:
        scale = 1200 / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    return img


def run_ocr_on_image(img: np.ndarray, ocr) -> str:
    """OCR a single in-memory image (numpy BGR array). Returns plain text."""
    try:
        img = _preprocess(img)
        result = ocr.ocr(img)
        if not result:
            return ""
        texts = [word[1][0] for line in result for word in line]
        gc.collect()
        return " ".join(texts)
    except Exception as e:
        print(f"[OCR] Image OCR failed: {e}")
        return ""


def run_ocr_on_image_file(image_path: str) -> str:
    """OCR a standalone image file (JPG, PNG, TIFF, BMP, …). Returns plain text."""
    try:
        img = cv2.imread(image_path)
        if img is None:
            print(f"[OCR] Could not read image file: {image_path}")
            return ""
        ocr = _get_ocr()
        return run_ocr_on_image(img, ocr)
    except Exception as e:
        print(f"[OCR] Image file OCR failed: {e}")
        return ""


def _pdf_page_to_bgr(page: "fitz.Page") -> np.ndarray:
    pix = page.get_pixmap()
    img = np.frombuffer(pix.samples, dtype=np.uint8)
    if pix.n == 4:
        img = img.reshape(pix.height, pix.width, 4)
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    else:
        img = img.reshape(pix.height, pix.width, 3)
    return img


def run_ocr_on_pdf(pdf_path: str) -> str:
    """
    OCR every page of a PDF and return full text.
    Pages are joined with double-newline so pipeline.py can reconstruct
    per-page structure.
    """
    try:
        print(f"[OCR] Converting PDF → images: {pdf_path}")
        ocr = _get_ocr()

        page_texts: list[str] = []
        with fitz.open(pdf_path) as pdf:
            total = pdf.page_count
            for i, page in enumerate(pdf):
                print(f"[OCR] Page {i + 1}/{total}")
                img = _pdf_page_to_bgr(page)
                text = run_ocr_on_image(img, ocr)
                page_texts.append(text)
                del img
                gc.collect()

        return "\n\n".join(page_texts).strip()

    except Exception as e:
        print(f"[OCR] PDF OCR failed: {e}")
        return ""
