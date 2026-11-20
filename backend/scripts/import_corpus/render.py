"""
Write a case's content in the file format a school would send it in.

A layout (layouts.py) produces Sheets - rows of text with merged cells and
lines of text above the table - and these writers turn them into .xlsx (one
tab each, or all stacked on one tab), .csv, .docx, .pdf, a clean .png, and a
.jpg that looks like a phone photo of a printout.
"""
from __future__ import annotations

import csv
import io
import random
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Sheet:
    name: str
    rows: list[list[str]]
    merges: list[tuple[int, int, int, int]] = field(default_factory=list)  # r1, c1, r2, c2 (0-based, inclusive)
    notes_above: list[str] = field(default_factory=list)                   # title lines before the table


def _stacked(sheets: list[Sheet]) -> tuple[list[list[str]], list[tuple[int, int, int, int]]]:
    """Every sheet one after another on one grid, a blank row between."""
    rows: list[list[str]] = []
    merges = []
    for sh in sheets:
        for line in sh.notes_above:
            rows.append([line])
        base = len(rows)
        rows += [list(r) for r in sh.rows]
        merges += [(a + base, b, c + base, d) for a, b, c, d in sh.merges]
        rows.append([])
    return rows, merges


def write_xlsx(path: Path, sheets: list[Sheet], one_tab: bool) -> None:
    import openpyxl
    from openpyxl.styles import Alignment, Font

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    groups = [("Sheet1", _stacked(sheets))] if one_tab else [(sh.name[:31], _stacked([sh])) for sh in sheets]
    seen = set()
    for name, (rows, merges) in groups:
        title = name or "Sheet"
        while title in seen:
            title = title[:28] + "_" + str(len(seen))
        seen.add(title)
        ws = wb.create_sheet(title)
        for r, row in enumerate(rows, start=1):
            for c, val in enumerate(row, start=1):
                if val != "":
                    ws.cell(r, c, _num(val))
        for a, b, c, d in merges:
            if (a, b) == (c, d):
                continue
            try:
                ws.merge_cells(start_row=a + 1, start_column=b + 1, end_row=c + 1, end_column=d + 1)
                ws.cell(a + 1, b + 1).alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            except ValueError:
                pass
        for r in range(1, min(len(rows), 3) + 1):
            for cell in ws[r]:
                cell.font = Font(bold=True)
    wb.save(path)


def _num(val: str):
    """Numbers as numbers, the way Excel stores a typed period count."""
    if isinstance(val, str) and val.isdigit() and len(val) < 4:
        return int(val)
    return val


def write_csv(path: Path, sheets: list[Sheet]) -> None:
    rows, _ = _stacked(sheets)
    width = max((len(r) for r in rows), default=0)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for r in rows:
            w.writerow(r + [""] * (width - len(r)))


def write_docx(path: Path, sheets: list[Sheet]) -> None:
    import docx

    d = docx.Document()
    for sh in sheets:
        for line in sh.notes_above:
            d.add_paragraph(line)
        if not sh.rows:
            continue
        width = max(len(r) for r in sh.rows)
        t = d.add_table(rows=len(sh.rows), cols=width)
        t.style = "Table Grid"
        for r, row in enumerate(sh.rows):
            for c in range(width):
                t.cell(r, c).text = row[c] if c < len(row) else ""
        for a, b, c, e in sh.merges:
            if (a, b) != (c, e) and c < len(sh.rows) and e < width:
                try:
                    keep = t.cell(a, b).text
                    merged = t.cell(a, b).merge(t.cell(c, e))
                    merged.text = keep
                except Exception:
                    pass
        d.add_paragraph("")
    d.save(path)


def write_pdf(path: Path, sheets: list[Sheet], landscape_page: bool = True) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4) if landscape_page else A4,
                            leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)
    story = []
    for sh in sheets:
        for line in sh.notes_above:
            story.append(Paragraph(_esc(line), styles["Heading4"]))
        if sh.rows:
            width = max(len(r) for r in sh.rows)
            data = [[Paragraph(_esc(c), styles["BodyText"]) for c in (r + [""] * (width - len(r)))] for r in sh.rows]
            t = Table(data, repeatRows=0)
            style = [("GRID", (0, 0), (-1, -1), 0.5, colors.black), ("FONTSIZE", (0, 0), (-1, -1), 7),
                     ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
            for a, b, c, e in sh.merges:
                if (a, b) != (c, e):
                    style.append(("SPAN", (b, a), (e, c)))
            t.setStyle(TableStyle(style))
            story.append(t)
        story.append(Spacer(1, 14))
    doc.build(story)


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_image(path: Path, sheets: list[Sheet], rng: random.Random, photo: bool) -> None:
    """The table drawn as a printout. `photo`: slightly turned, uneven light,
    soft focus and JPEG artefacts - a phone picture of the notice board copy."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    rows, merges = _stacked(sheets)
    width = max((len(r) for r in rows), default=1)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    try:
        font = ImageFont.truetype(font_path, 15)
    except OSError:
        font = ImageFont.load_default()
    col_w = [90] * width
    for r in rows:
        if len(r) == 1 and width > 1:
            continue  # a title line spans the table; it doesn't size column 1
        for c, v in enumerate(r):
            longest = max((font.getlength(part) for part in v.split("\n")), default=0) if v else 0
            col_w[c] = max(col_w[c], int(longest) + 14)
    row_h = 46 if any("\n" in v for r in rows for v in r) else 28
    W, H = sum(col_w) + 40, len(rows) * row_h + 40
    img = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(img)
    covered = set()
    span = {}
    for a, b, c, d in merges:
        span[(a, b)] = (c, d)
        for rr in range(a, c + 1):
            for cc in range(b, d + 1):
                if (rr, cc) != (a, b):
                    covered.add((rr, cc))
    x0s = [20 + sum(col_w[:c]) for c in range(width + 1)]
    for r, row in enumerate(rows):
        y = 20 + r * row_h
        if not row:
            continue
        if len(row) == 1 and width > 1:  # a title line
            dr.text((x0s[0], y + 6), row[0], fill="black", font=font)
            continue
        for c in range(width):
            if (r, c) in covered:
                continue
            c2r, c2c = span.get((r, c), (r, c))
            box = (x0s[c], y, x0s[c2c + 1], 20 + (c2r + 1) * row_h)
            dr.rectangle(box, outline="black", width=1)
            v = row[c] if c < len(row) else ""
            if v:
                dr.text((box[0] + 6, box[1] + 6), v, fill="black", font=font)
    if photo:
        img = img.rotate(rng.uniform(-3, 3), expand=True, fillcolor=(235, 232, 225))
        shade = Image.linear_gradient("L").resize(img.size).point(lambda p: 200 + p // 5)
        img = Image.composite(img, Image.new("RGB", img.size, (215, 210, 200)), shade)
        img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.4, 1.0)))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=rng.randint(45, 70))
        path.write_bytes(buf.getvalue())
    else:
        img.save(path)
