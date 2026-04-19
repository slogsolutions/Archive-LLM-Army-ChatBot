import cv2
import gc
import numpy as np
import fitz  # 🔥 PyMuPDF (NO poppler needed)
from paddleocr import PaddleOCR


# OCR init (optimized)
ocr = PaddleOCR(
    use_gpu=False,
    use_angle_cls=True,
    lang="en",
    rec_batch_num=2,
    cpu_threads=4
)


# resize (important)
def preprocess_image(img):
    h, w = img.shape[:2]

    if max(h, w) > 1200:
        scale = 1200 / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)))

    return img


# OCR on single image
def run_ocr_on_image(img):
    try:
        img = preprocess_image(img)

        result = ocr.ocr(img)

        text = ""
        for line in result:
            for word in line:
                text += word[1][0] + " "

        gc.collect()
        return text.strip()

    except Exception as e:
        print("❌ OCR FAILED:", str(e))
        return ""


# 🔥 PDF → images using PyMuPDF (NO poppler)
def pdf_to_images(pdf_path):
    images = []
    doc = fitz.open(pdf_path)

    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap()

        img = np.frombuffer(pix.samples, dtype=np.uint8)
        img = img.reshape(pix.height, pix.width, 3)

        images.append(img)

    return images


# 🔥 MAIN FUNCTION (FINAL)
def run_ocr_on_pdf(pdf_path):
    try:
        print("📄 Converting PDF → images (PyMuPDF)...")

        images = pdf_to_images(pdf_path)

        full_text = ""

        for i, img in enumerate(images):
            print(f"📄 Processing page {i+1}/{len(images)}")

            page_text = run_ocr_on_image(img)
            full_text += page_text + "\n"

        return full_text.strip()

    except Exception as e:
        print("❌ PDF OCR FAILED:", str(e))
        return ""