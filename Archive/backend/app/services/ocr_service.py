def run_ocr(file_path: str) -> str:
    """
    Main OCR entry point
    Switch engine here (Paddle / Device / API)
    """

    # 🔹 CURRENT: PaddleOCR
    return paddle_ocr(file_path)


# =========================
# PADDLE IMPLEMENTATION
# =========================
def paddle_ocr(file_path: str) -> str:
    from paddleocr import PaddleOCR

    ocr = PaddleOCR(use_angle_cls=True, lang='en')

    result = ocr.ocr(file_path)

    text = ""
    for line in result[0]:
        text += line[1][0] + "\n"

    return text


# =========================
# FUTURE DEVICE (placeholder)
# =========================
def device_ocr(file_path: str) -> str:
    """
    Replace later with your OCR hardware API
    """
    return "DEVICE OCR RESULT"