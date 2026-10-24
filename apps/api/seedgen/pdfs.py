"""PDF rendering for the seed: lecture decks, typed homework uploads and scanned exam papers.

Only fonts bundled with fpdf2 (Helvetica, Latin-1) and Pillow (its default FreeType font) are
used, so output is the same on every machine. Neither covers math symbols, hence `ascii_math`.
Scanned exams are JPEG images placed on PDF pages: no text layer, like a real scanner.
"""

import random
import textwrap
from datetime import UTC, datetime
from io import BytesIO

from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont

from seedgen.content import CourseSpec, Material
from seedgen.simulate import SubResult

PDF_DATE = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)

_ASCII = str.maketrans({
    "₁": "1", "₂": "2", "ⱼ": "j", "≥": ">=", "≤": "<=", "−": "-", "⁺": "+", "⁻": "-",
    "—": "-", "–": "-", "·": "*", "“": '"', "”": '"', "’": "'", "…": "...", "→": "->",
})


def ascii_math(text: str) -> str:
    return text.translate(_ASCII).encode("latin-1", "replace").decode("latin-1")


def _new_pdf(**kwargs) -> FPDF:
    pdf = FPDF(**kwargs)
    pdf.set_creation_date(PDF_DATE)
    pdf.set_auto_page_break(True, margin=15)
    return pdf


def _bytes(pdf: FPDF) -> bytes:
    return bytes(pdf.output())


# -- lecture decks and readings --------------------------------------------------------------

def material_pdf(course: CourseSpec, material: Material) -> tuple[bytes, int]:
    if material.kind == "slides":
        pdf = _new_pdf(orientation="L", unit="mm", format=(143, 254))
        pages = [(material.title, (course.weeks.get(material.week, ""), f"{course.code} - {course.name}"))]
        pages += list(material.slides)
        for i, (heading, bullets) in enumerate(pages):
            pdf.add_page()
            pdf.set_fill_color(39, 53, 64)
            pdf.rect(0, 0, 254, 28, "F")
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("Helvetica", "B", 22 if i == 0 else 18)
            pdf.set_xy(14, 8)
            pdf.cell(226, 12, ascii_math(heading))
            pdf.set_text_color(39, 53, 64)
            pdf.set_font("Helvetica", "", 15)
            pdf.set_xy(14, 40)
            for bullet in bullets:
                pdf.set_x(14)
                pdf.multi_cell(226, 9, ("" if i == 0 else "-  ") + ascii_math(bullet), new_x="LMARGIN", new_y="NEXT")
                pdf.ln(2)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_xy(14, 132)
            pdf.cell(226, 5, f"{course.code}  |  Week {material.week}  |  {i + 1}", align="R")
        return _bytes(pdf), len(pages)

    pdf = _new_pdf(unit="mm", format="Letter")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.multi_cell(0, 10, ascii_math(material.title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, f"{course.code} {course.name} - {course.weeks.get(material.week, '')}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    for heading, paragraphs in material.slides:
        for para in paragraphs:
            pdf.multi_cell(0, 6, ascii_math(para) + " " + ascii_math(_FILLER), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
    return _bytes(pdf), pdf.page_no()


_FILLER = (
    "Work each example yourself before reading the solution, and check your model against the "
    "checklist at the end of this note: units on every variable, the sense of the objective, the "
    "direction of each inequality, and non-negativity."
)


# -- typed homework uploads ------------------------------------------------------------------

def typed_submission_pdf(course: CourseSpec, sub: SubResult) -> tuple[bytes, int]:
    spec = sub.assessment
    pdf = _new_pdf(unit="mm", format="Letter")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.multi_cell(0, 8, ascii_math(f"{course.code} - {spec.title}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, ascii_math(f"{sub.student.name}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    stems_done: set[str] = set()
    for r in sub.questions:
        q = r.question
        if q.parent and q.parent not in stems_done:
            stems_done.add(q.parent)
            pdf.set_font("Helvetica", "B", 11)
            pdf.multi_cell(0, 6, ascii_math(f"{q.parent}. {spec.stems.get(q.parent, '')}"), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
        pdf.set_font("Helvetica", "B", 11)
        pdf.multi_cell(0, 6, ascii_math(f"{q.key}) {q.prompt}"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(0, 6, ascii_math(r.response or "(no answer)"), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)
    return _bytes(pdf), pdf.page_no()


# -- scanned exams ---------------------------------------------------------------------------

PAGE_W, PAGE_H = 1000, 1294
PAPER = (247, 245, 238)
PRINT = (45, 45, 45)
INK = (32, 56, 140)
RED = (190, 30, 30)


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)  # type: ignore[return-value]


def _handwrite(draw: ImageDraw.ImageDraw, rng: random.Random, x: int, y: int, text: str,
               size: int, color: tuple[int, int, int], width: int = 52) -> int:
    """Draw text word by word with small jitter so it reads as handwriting. Returns new y."""
    font = _font(size)
    for line in textwrap.wrap(ascii_math(text), width) or [""]:
        cx = x + rng.randint(-4, 4)
        for word in line.split(" "):
            draw.text((cx, y + rng.randint(-2, 2)), word, font=font, fill=color)
            cx += int(draw.textlength(word + " ", font=font)) + rng.randint(-1, 3)
        y += size + 10
    return y


def _scan_page(rng: random.Random, course: CourseSpec, sub: SubResult, parent: str, page: int,
               pages: int) -> bytes:
    spec = sub.assessment
    img = Image.new("RGB", (PAGE_W, PAGE_H), PAPER)
    draw = ImageDraw.Draw(img)
    small, body = _font(18), _font(20)
    draw.text((60, 40), f"{course.code} {spec.title} - {course.term}", font=body, fill=PRINT)
    draw.text((PAGE_W - 170, 40), f"Page {page} of {pages}", font=small, fill=PRINT)
    draw.text((60, 80), "Name:", font=body, fill=PRINT)
    _handwrite(draw, rng, 140, 76, sub.student.name, 26, INK)
    draw.line((60, 120, PAGE_W - 60, 120), fill=PRINT, width=2)

    y = 140
    for line in textwrap.wrap(ascii_math(f"{parent}. {spec.stems.get(parent, '')}"), 80):
        draw.text((60, y), line, font=body, fill=PRINT)
        y += 28
    y += 10
    for r in (r for r in sub.questions if r.question.parent == parent):
        q = r.question
        for line in textwrap.wrap(ascii_math(f"({q.key[-1]}) {q.prompt}  [{q.points:g} pts]"), 80):
            draw.text((60, y), line, font=body, fill=PRINT)
            y += 28
        y = _handwrite(draw, rng, 90, y + 12, r.response or "", 26, INK) + 6
        mark = f"{(r.points or 0):g}/{q.points:g}"
        mx, my = PAGE_W - 150, y - 50
        draw.text((mx, my), mark, font=_font(30), fill=RED)
        draw.ellipse((mx - 12, my - 8, mx + 100, my + 42), outline=RED, width=3)
        if r.comment:
            y = _handwrite(draw, rng, 110, y, r.comment, 20, RED, width=70)
        y += 60

    img = img.rotate(rng.uniform(-0.6, 0.6), resample=Image.Resampling.BICUBIC, fillcolor=PAPER)
    out = BytesIO()
    img.save(out, "JPEG", quality=55)
    return out.getvalue()


def scanned_exam_pdf(course: CourseSpec, sub: SubResult, rng: random.Random) -> tuple[bytes, int]:
    spec = sub.assessment
    parents = sorted(spec.pages, key=spec.pages.get)  # type: ignore[arg-type]
    pdf = _new_pdf(unit="pt", format=(612, 792))
    pdf.set_auto_page_break(False)
    for parent in parents:
        jpeg = _scan_page(rng, course, sub, parent, spec.pages[parent], len(parents))
        pdf.add_page()
        pdf.image(BytesIO(jpeg), x=0, y=0, w=612, h=792)
    return _bytes(pdf), len(parents)
