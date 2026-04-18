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

    if not result:
        return ""

    text_lines = []

    for page in result:
        if page:
            for line in page:
                if line and len(line) > 1:
                    txt = line[1][0].strip()
                    if txt:
                        text_lines.append(txt)

    return "\n".join(text_lines)


# =========================
# FUTURE DEVICE (placeholder)
# =========================
def device_ocr(file_path: str) -> str:
    """
    Replace later with your OCR hardware API
    """
    return "DEVICE OCR RESULT"