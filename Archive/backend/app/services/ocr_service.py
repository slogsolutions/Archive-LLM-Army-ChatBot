import cv2
import gc
import numpy as np
import fitz  # PyMuPDF


# ✅ Lazy OCR loader (CRITICAL FIX)
def get_ocr():
    from paddleocr import PaddleOCR
    return PaddleOCR(
        use_gpu=False,
        use_angle_cls=True,
        lang="en",
        rec_batch_num=2,
        cpu_threads=4
    )


# ✅ Resize (safe)
def preprocess_image(img):
    h, w = img.shape[:2]

    if max(h, w) > 1200:
        scale = 1200 / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)))

    return img


# ✅ OCR on single image (SAFE)
def run_ocr_on_image(img, ocr):
    try:
        img = preprocess_image(img)

        result = ocr.ocr(img)

        if not result:
            return ""

        text = []
        for line in result:
            for word in line:
                text.append(word[1][0])

        gc.collect()
        return " ".join(text)

    except Exception as e:
        print("❌ OCR FAILED:", str(e))
        return ""


# ✅ PDF → images (FIXED for RGB/RGBA)
def pdf_to_images(pdf_path):
    images = []

    with fitz.open(pdf_path) as doc:  # auto close
        for page in doc:
            pix = page.get_pixmap()

            img = np.frombuffer(pix.samples, dtype=np.uint8)

            # 🔥 Handle different channels safely
            if pix.n == 4:
                img = img.reshape(pix.height, pix.width, 4)
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            else:
                img = img.reshape(pix.height, pix.width, 3)

            images.append(img)

    return images


# ✅ MAIN FUNCTION (CELERY SAFE)
def run_ocr_on_pdf(pdf_path):
    try:
        print("📄 Converting PDF → images (PyMuPDF)...")

        ocr = get_ocr()  # 🔥 initialize HERE (not global)

        images = pdf_to_images(pdf_path)

        full_text = []

        for i, img in enumerate(images):
            print(f"📄 Processing page {i+1}/{len(images)}")

            page_text = run_ocr_on_image(img, ocr)
            full_text.append(page_text)

            # free memory per page
            del img
            gc.collect()

        return "\n".join(full_text).strip()

    except Exception as e:
        print("❌ PDF OCR FAILED:", str(e))
        return ""