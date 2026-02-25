"""OCR processor: extracts text from image files and scanned PDFs via Tesseract."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}


def process_file(source_path: Path, ocr_output_dir: Path) -> dict:
    """Run OCR on *source_path* and write the result to *ocr_output_dir*.

    Works for:
    - Image files (PNG, JPG, JPEG, TIFF, BMP).
    - Scanned PDFs (each page is converted to an image and OCR'd).

    Args:
        source_path: Path to the evidence file.
        ocr_output_dir: Directory where the ``.txt`` output is stored.

    Returns:
        A dict with ``output_file``, ``text``, ``confidence``, and ``error`` keys.
    """
    ocr_output_dir.mkdir(parents=True, exist_ok=True)
    ext = source_path.suffix.lower()

    try:
        if ext in IMAGE_EXTENSIONS:
            return _ocr_image(source_path, ocr_output_dir)
        if ext == ".pdf":
            return _ocr_pdf(source_path, ocr_output_dir)
        return {
            "output_file": None,
            "text": "",
            "confidence": None,
            "error": f"Unsupported file type for OCR: {ext}",
        }
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("OCR failed for %s: %s", source_path, exc)
        return {"output_file": None, "text": "", "confidence": None, "error": str(exc)}


def is_image_based(path: Path) -> bool:
    """Return ``True`` if *path* is an image or a scanned (image-only) PDF."""
    ext = path.suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return True
    if ext == ".pdf":
        return _pdf_is_scanned(path)
    return False


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _ocr_image(source_path: Path, ocr_output_dir: Path) -> dict:
    import pytesseract  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    img = Image.open(source_path)
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    text = " ".join(w for w in data["text"] if w.strip())
    confidences = [c for c in data["conf"] if isinstance(c, (int, float)) and c >= 0]
    avg_conf = sum(confidences) / len(confidences) if confidences else None

    output_file = ocr_output_dir / (source_path.stem + "_ocr.txt")
    output_file.write_text(text, encoding="utf-8")
    logger.info("OCR complete for %s (confidence=%.1f)", source_path.name, avg_conf or 0)
    return {"output_file": output_file, "text": text, "confidence": avg_conf, "error": None}


def _ocr_pdf(source_path: Path, ocr_output_dir: Path) -> dict:
    from pdf2image import convert_from_path  # noqa: PLC0415
    import pytesseract  # noqa: PLC0415

    pages = convert_from_path(str(source_path))
    all_text_parts: list[str] = []
    all_confidences: list[float] = []

    for page_num, page_img in enumerate(pages, start=1):
        data = pytesseract.image_to_data(page_img, output_type=pytesseract.Output.DICT)
        page_text = " ".join(w for w in data["text"] if w.strip())
        all_text_parts.append(f"[Page {page_num}]\n{page_text}")
        confs = [c for c in data["conf"] if isinstance(c, (int, float)) and c >= 0]
        all_confidences.extend(confs)

    full_text = "\n\n".join(all_text_parts)
    avg_conf = sum(all_confidences) / len(all_confidences) if all_confidences else None

    output_file = ocr_output_dir / (source_path.stem + "_ocr.txt")
    output_file.write_text(full_text, encoding="utf-8")
    return {"output_file": output_file, "text": full_text, "confidence": avg_conf, "error": None}


def _pdf_is_scanned(path: Path) -> bool:
    """Heuristic: a PDF is considered scanned if it contains no selectable text."""
    try:
        import pdfplumber  # noqa: PLC0415

        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                if page.extract_text():
                    return False
        return True
    except Exception:  # pylint: disable=broad-except
        return False
