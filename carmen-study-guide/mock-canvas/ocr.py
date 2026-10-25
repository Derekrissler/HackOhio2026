"""
Text extraction for submitted work (spec §4): PDFs and images of typed or handwritten answers.

Per page: use the PDF's own text layer when it has one (typed work); otherwise render the page at 300 dpi
and run Tesseract. Every line comes back with a page-relative bounding box [x1, y1, x2, y2] (0-1) and, for
OCR, Tesseract's confidence (0-100). Pages that are empty or low-confidence are flagged, never guessed at.
Tesseract is good on printed text and weak on handwriting; low confidence is the signal to review by hand.

Results are cached by file hash in .ocr_cache/, so re-syncing doesn't re-OCR unchanged files.
"""

import io
import json
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image, ImageOps

EXTRACTOR_VERSION = "ocr-1"
DPI = 300
NATIVE_MIN_CHARS = 25      # fewer characters than this in the text layer -> treat the page as a scan
LOW_CONFIDENCE = 60        # mean word confidence below this flags the page / line for review
CACHE = Path(__file__).resolve().parent / ".ocr_cache"


def engine() -> str:
    return f"tesseract-{pytesseract.get_tesseract_version()}"


def _norm(box, w, h) -> list[float]:
    x0, y0, x1, y1 = box
    return [round(max(0.0, min(1.0, v)), 4) for v in (x0 / w, y0 / h, x1 / w, y1 / h)]


def _native_page(page) -> dict:
    w, h = page.rect.width, page.rect.height
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"]).strip()
            if text:
                lines.append({"text": text, "bbox_norm": _norm(line["bbox"], w, h), "confidence": None})
    return {"method": "native_text", "text": "\n".join(l["text"] for l in lines), "mean_confidence": None,
            "lines": lines, "flags": []}


def _ocr_image(img: Image.Image) -> dict:
    img = ImageOps.exif_transpose(img).convert("L")
    d = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, config="--psm 3")
    groups: dict = {}
    for i, word in enumerate(d["text"]):
        conf = float(d["conf"][i])
        if not word.strip() or conf < 0:
            continue
        key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        g = groups.setdefault(key, {"words": [], "confs": [], "box": [1e9, 1e9, 0, 0]})
        g["words"].append(word)
        g["confs"].append(conf)
        x, y, bw, bh = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
        b = g["box"]
        g["box"] = [min(b[0], x), min(b[1], y), max(b[2], x + bw), max(b[3], y + bh)]
    lines, all_confs = [], []
    for key in sorted(groups):
        g = groups[key]
        conf = sum(g["confs"]) / len(g["confs"])
        all_confs += g["confs"]
        lines.append({"text": " ".join(g["words"]), "bbox_norm": _norm(g["box"], img.width, img.height),
                      "confidence": round(conf, 1), **({"low_confidence": True} if conf < LOW_CONFIDENCE else {})})
    mean = round(sum(all_confs) / len(all_confs), 1) if all_confs else None
    flags = ["no_text_found"] if not lines else (["low_confidence"] if mean < LOW_CONFIDENCE else [])
    # Tesseract can be confidently wrong on handwriting, so a page where many lines are shaky needs review
    # even when its average looks fine.
    if lines and sum(1 for l in lines if l.get("low_confidence")) / len(lines) >= 0.25:
        flags.append("needs_review")
    return {"method": "ocr", "text": "\n".join(l["text"] for l in lines), "mean_confidence": mean,
            "lines": lines, "flags": flags}


def _analyze(data: bytes, content_type: str) -> dict:
    pages = []
    if content_type.startswith("image/"):
        pages.append({"page": 1, **_ocr_image(Image.open(io.BytesIO(data)))})
    else:
        doc = pymupdf.open(stream=data, filetype="pdf")
        for n, page in enumerate(doc, 1):
            if len(page.get_text("text").strip()) >= NATIVE_MIN_CHARS:
                pages.append({"page": n, **_native_page(page)})
            else:
                pix = page.get_pixmap(dpi=DPI)
                img = Image.frombytes("RGB" if pix.n < 4 else "RGBA", (pix.width, pix.height), pix.samples)
                pages.append({"page": n, **_ocr_image(img)})
    ocr_confs = [p["mean_confidence"] for p in pages if p["mean_confidence"] is not None]
    flags = sorted({f for p in pages for f in p["flags"]})
    return {"extractor_version": EXTRACTOR_VERSION, "engine": engine(), "page_count": len(pages),
            "methods": sorted({p["method"] for p in pages}),
            "mean_confidence": round(sum(ocr_confs) / len(ocr_confs), 1) if ocr_confs else None,
            "flags": flags, "pages": pages}


def analyze(data: bytes, content_type: str, sha256_hex: str) -> dict:
    """Extract text from a PDF or image, using the cache when this exact file was already analyzed."""
    path = CACHE / f"{sha256_hex}.{EXTRACTOR_VERSION}.json"
    if path.is_file():
        return json.loads(path.read_text())
    result = _analyze(data, content_type or "application/pdf")
    CACHE.mkdir(exist_ok=True)
    path.write_text(json.dumps(result))
    return result
