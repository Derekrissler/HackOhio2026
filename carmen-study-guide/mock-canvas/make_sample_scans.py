"""
Generate fictional sample submissions (PDFs) to exercise OCR, from the excerpts in 07_written_feedback.md.

    .venv/bin/python make_sample_scans.py            # writes CourseContent/sample_submissions/*.pdf
    .venv/bin/python make_sample_scans.py --upload   # ...and uploads them via the instructor scan page (server on :8001)

Four styles: a scanned typed page, two scanned "handwritten" pages (one clean, one tilted and noisy), and a
typed PDF with a real text layer. All content and names are fictional.
"""

import random
import re
import sys
from pathlib import Path

import pymupdf
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "CourseContent" / "07_written_feedback.md"
OUT = HERE.parent / "CourseContent" / "sample_submissions"
FONTS = Path("/System/Library/Fonts")
W, H, MARGIN = 2550, 3300, 200  # US letter at 300 dpi


def excerpts() -> dict[str, str]:
    """Each feedback section's 'Excerpt of submission' / 'Student Response' text, keyed by section heading."""
    out = {}
    for part in re.split(r"^---\s*$", SRC.read_text(), flags=re.M):
        head = re.search(r"^## (.+)$", part, flags=re.M)
        body = re.search(r"### (?:Excerpt of submission.*?|Student Response.*?)\n(.*?)(?=\n### Rubric Breakdown)",
                         part, flags=re.S)
        if head and body:
            text = re.sub(r"^```\w*\s*$", "", body.group(1), flags=re.M)
            text = re.sub(r"^### Excerpt of prompt log\s*$", "Prompt log:", text, flags=re.M)
            text = re.sub(r"^> ?", "", text, flags=re.M).replace("**", "")
            out[head.group(1).strip()] = re.sub(r"\n{3,}", "\n\n", text).strip()
    return out


def wrap(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines = []
    for para in text.splitlines():
        line = ""
        for word in para.split(" "):
            trial = f"{line} {word}" if line else word
            if font.getlength(trial) <= width:
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def scanned_page(header: str, text: str, font_file: str, size: int, *, tilt=0.0, noise=0, jitter=0, seed=1) -> Image.Image:
    rnd = random.Random(seed)
    font = ImageFont.truetype(str(FONTS / font_file), size)
    head_font = ImageFont.truetype(str(FONTS / font_file), int(size * 1.15))
    img = Image.new("L", (W, H), 250)
    draw = ImageDraw.Draw(img)
    y = MARGIN
    draw.text((MARGIN, y), header, font=head_font, fill=25)
    y += int(size * 2.4)
    for line in wrap(text, font, W - 2 * MARGIN):
        draw.text((MARGIN + rnd.randint(-jitter, jitter), y + rnd.randint(-jitter, jitter)), line, font=font, fill=30)
        y += int(size * 1.45)
        if y > H - MARGIN:
            break
    if noise:  # scanner speckle
        px = img.load()
        for _ in range(noise):
            px[rnd.randrange(W), rnd.randrange(H)] = rnd.choice((90, 140, 200))
    if tilt:
        img = img.rotate(tilt, resample=Image.BICUBIC, fillcolor=250, expand=False)
    return img.filter(ImageFilter.GaussianBlur(0.6))


def typed_text_pdf(header: str, text: str, path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_textbox(pymupdf.Rect(54, 54, 558, 760), f"{header}\n\n{text}", fontname="helv", fontsize=10.5)
    doc.save(path)


SAMPLES = [  # (feedback section, student id, name, assignment id, file stem, style)
    ("Assignment 1 Feedback", 5003, "Jordan Patel", 2001, "jordan_patel_A1_typed_scan", "typed_scan"),
    ("Assignment 3 Feedback", 5011, "Priya Shah", 2003, "priya_shah_A3_handwritten", "handwritten"),
    ("Midterm Feedback", 5010, "Leo Martinez", 2201, "leo_martinez_midterm_messy_scan", "messy"),
    ("Final Exam Feedback", 5015, "Zoe Campbell", 2202, "zoe_campbell_final_typed_text", "native"),
]


def main(upload: bool) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    found = excerpts()
    made = []
    for section, uid, name, aid, stem, style in SAMPLES:
        key = next((k for k in found if k.startswith(section)), None)
        if not key:
            print(f"skip {stem}: no excerpt under '{section}'")
            continue
        header = f"{name}    VIBE 101    {key.split(':', 1)[-1].strip().split('(')[0] or section}"
        path = OUT / f"{stem}.pdf"
        if style == "native":
            typed_text_pdf(header, found[key], path)
        else:
            img = {"typed_scan": lambda: scanned_page(header, found[key], "Supplemental/Courier New.ttf", 46, tilt=0.4, noise=4000),
                   "handwritten": lambda: scanned_page(header, found[key], "Supplemental/Bradley Hand Bold.ttf", 58, jitter=3),
                   "messy": lambda: scanned_page(header, found[key], "Noteworthy.ttc", 60, tilt=1.6, noise=25000, jitter=6),
                   }[style]()
            img.save(path, "PDF", resolution=300)
        made.append((path, uid, aid))
        print(f"wrote {path.relative_to(HERE.parent)}  ({style})")
    if upload:
        for path, uid, aid in made:
            r = requests.post("http://localhost:8001/courses/1001/scans", allow_redirects=False,
                              data={"user_id": uid, "assignment_id": aid},
                              files={"file": (path.name, path.read_bytes(), "application/pdf")})
            print(f"uploaded {path.name} -> student {uid}, assignment {aid}: HTTP {r.status_code}")


if __name__ == "__main__":
    main("--upload" in sys.argv)
