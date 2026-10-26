"""
One day's substitutions, as a summary: who is on leave, and period by period
who is covering whom - for one part of the school or all of it.

Cover is saved per date and per part (primary, middle, ...), possibly in
several sittings, so a day's summary is put together from every record for
that date. A later record replaces an earlier one's entry for the same
lesson, which is what "saving again" means.

Records from before dates were kept have none; they belong to the day they
were saved.
"""
from __future__ import annotations

import io
from datetime import date as date_type

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.models.school import ClassGroup, Period, School, Subject, SubstitutionLog, Teacher
from app.services.naming import name_sort_key
from app.services.school_categories import CATEGORIES, CATEGORY_LABELS, category_of
from app.services.timetable_structure import lesson_numbers


def log_date(log: SubstitutionLog) -> date_type | None:
    if log.date is not None:
        return log.date
    return log.created_at.date() if log.created_at else None


def _section_label(cg: ClassGroup | None) -> str:
    if cg is None:
        return "?"
    return f"{cg.grade} - {cg.name}" if cg.grade else cg.name


def build_summary(db: Session, school_id: int, day: date_type, category: str | None) -> dict:
    school = db.get(School, school_id)
    overrides = (school.grade_categories or {}) if school else {}
    logs = [
        log for log in db.query(SubstitutionLog)
        .filter(SubstitutionLog.school_id == school_id)
        .order_by(SubstitutionLog.id)
        .all()
        if log_date(log) == day
    ]
    periods = {p.id: p for p in db.query(Period).filter(Period.school_id == school_id)}
    numbers = lesson_numbers(periods.values())
    teachers = {t.id: t.name for t in db.query(Teacher).filter(Teacher.school_id == school_id)}
    sections = {c.id: c for c in db.query(ClassGroup).filter(ClassGroup.school_id == school_id)}
    subjects = {s.id: s.name for s in db.query(Subject).filter(Subject.school_id == school_id)}

    def period_label(period_id: int) -> str:
        if period_id in numbers:
            return f"Period {numbers[period_id]}"
        p = periods.get(period_id)
        return (p.label if p and p.label else "A period") if p else "A removed period"

    def category_for(change: dict) -> str | None:
        if change.get("category"):
            return change["category"]
        cg = sections.get(change.get("class_group_id"))
        return category_of(cg.grade if cg else None, overrides)

    # Later saves replace earlier ones for the same lesson.
    merged: dict[tuple, dict] = {}
    for log in logs:
        for change in log.changes or []:
            merged[(change["period_id"], change["class_group_id"], change["absent_teacher_id"])] = change

    rows = []
    for change in merged.values():
        cat = category_for(change)
        if category is not None and cat != category:
            continue
        rows.append((change, cat))

    def row_order(item):
        change, _ = item
        p = periods.get(change["period_id"])
        cg = sections.get(change["class_group_id"])
        return (p.order if p else 0, name_sort_key(_section_label(cg)))

    rows.sort(key=row_order)

    # Who is on leave: what was recorded, merged across the day's saves (the
    # whole day wins over some periods), limited to the teachers whose
    # absence matters to this part of the school.
    # A whole-school save names everyone; for one part, only those named in
    # that part's own saves, or whose lessons there needed cover, count.
    recorded: dict[int, set | None] = {}
    named_here: set[int] = set()
    for log in logs:
        if category is not None and log.category not in (None, category):
            continue
        for a in log.absences or []:
            tid = a.get("teacher_id")
            ids = a.get("period_ids")
            if category is None or log.category == category:
                named_here.add(tid)
            if tid in recorded and recorded[tid] is None:
                continue
            recorded[tid] = None if ids is None else (recorded.get(tid) or set()) | set(ids)
    relevant = {change["absent_teacher_id"] for change, _ in rows} | named_here
    on_leave = []
    for tid in relevant:
        if tid in recorded:
            ids = recorded[tid]
        else:
            # An older record kept no absences: the periods they were covered for.
            ids = {change["period_id"] for change, _ in rows if change["absent_teacher_id"] == tid}
        on_leave.append({
            "teacher_id": tid,
            "teacher": teachers.get(tid, "A teacher who has left"),
            "periods": None if ids is None else [
                period_label(pid) for pid in sorted(ids, key=lambda i: periods[i].order if i in periods else 0)
            ],
        })
    on_leave.sort(key=lambda x: name_sort_key(x["teacher"]))

    out_rows = []
    for change, cat in rows:
        sub = change.get("substituting_teacher_id")
        out_rows.append({
            "period": period_label(change["period_id"]),
            "class_group": _section_label(sections.get(change["class_group_id"])),
            "subject": subjects.get(change.get("subject_id")),
            "category": cat,
            "category_label": CATEGORY_LABELS.get(cat, "Other"),
            "absent_teacher": teachers.get(change["absent_teacher_id"], "A teacher who has left"),
            "substitute": teachers.get(sub, "A teacher who has left") if sub is not None else None,
        })
    return {
        "date": day,
        "weekday": day.strftime("%A"),
        "category": category,
        "category_label": CATEGORY_LABELS.get(category, "Whole school") if category else "Whole school",
        "on_leave": on_leave,
        "rows": out_rows,
        "uncovered": sum(1 for r in out_rows if r["substitute"] is None),
    }


def summary_pdf(summary: dict, school_name: str) -> bytes:
    """The summary on one A4 page per part - to print and pin up, or send."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.4 * cm, bottomMargin=1.4 * cm,
                            leftMargin=1.4 * cm, rightMargin=1.4 * cm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=styles["Heading1"], fontSize=16, spaceAfter=2)
    sub = ParagraphStyle("s", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#475569"))
    body = ParagraphStyle("b", parent=styles["Normal"], fontSize=10, leading=13)
    cell = ParagraphStyle("c", parent=styles["Normal"], fontSize=9, leading=11)

    def esc(text) -> str:
        return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    day = summary["date"]
    story = [
        Paragraph(f"Substitutions — {esc(summary['weekday'])}, {day.day} {day.strftime('%B %Y')}", title),
        Paragraph(esc(f"{school_name} · {summary['category_label']}"), sub),
        Spacer(1, 0.4 * cm),
    ]
    if summary["on_leave"]:
        leave = ", ".join(
            esc(p["teacher"]) + (" (whole day)" if p["periods"] is None else f" ({esc(', '.join(p['periods']))})")
            for p in summary["on_leave"]
        )
        story += [Paragraph(f"<b>On leave:</b> {leave}", body), Spacer(1, 0.3 * cm)]

    groups = [(summary["category_label"], summary["rows"])]
    if summary["category"] is None:
        order = [key for key, _ in CATEGORIES] + [None]
        groups = [
            (CATEGORY_LABELS.get(key, "Other"), [r for r in summary["rows"] if r["category"] == key])
            for key in order
        ]
        groups = [(label, rows) for label, rows in groups if rows]

    if not summary["rows"]:
        story.append(Paragraph("No lessons need cover.", body))
    for label, rows in groups:
        if summary["category"] is None:
            story += [Spacer(1, 0.2 * cm), Paragraph(f"<b>{esc(label)}</b>", body), Spacer(1, 0.1 * cm)]
        data = [["Period", "Class", "Subject", "On leave", "Replaced by"]]
        for r in rows:
            data.append([
                Paragraph(esc(r["period"]), cell), Paragraph(esc(r["class_group"]), cell),
                Paragraph(esc(r["subject"] or ""), cell), Paragraph(esc(r["absent_teacher"]), cell),
                Paragraph(esc(r["substitute"]) if r["substitute"] else "<font color='#b91c1c'><b>Not covered</b></font>", cell),
            ])
        table = Table(data, colWidths=[2.3 * cm, 3.4 * cm, 3.4 * cm, 4 * cm, 4.2 * cm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ]))
        story.append(table)
    if summary["uncovered"]:
        n = summary["uncovered"]
        story += [Spacer(1, 0.3 * cm), Paragraph(
            f"<font color='#b91c1c'><b>{n} period{'' if n == 1 else 's'} still need{'s' if n == 1 else ''} cover.</b></font>",
            body)]
    doc.build(story)
    return buf.getvalue()
