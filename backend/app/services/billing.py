"""
Granting a plan and issuing an invoice - the two things that happen whenever
money is received, whether through Cashfree checkout (app/routers/payments.py)
or recorded by hand for a bank transfer (app/routers/admin.py). Both paths call
these, so a school ends up in exactly the same state either way.
"""
import io
import logging
from datetime import datetime, timedelta, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.payment import Invoice, PlanOffer
from app.models.school import School

logger = logging.getLogger(__name__)


def _naive(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def grant_plan(
    db: Session,
    school: School,
    plan_id: str,
    period_days: int,
    offer: PlanOffer | None = None,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Put `school` on `plan_id` for `period_days`. Returns (start, end).

    Paying again while the same plan is still active adds the time after the
    current end date, so renewing early never loses days. Paying after it has
    lapsed (grace or locked) starts from today. A custom offer's limits are
    stored on the school; a Pro payment clears any old custom limits.
    Does not commit."""
    now = now or datetime.now(timezone.utc)
    current = school.plan_valid_until
    if current is not None and current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    start = current if (current and current > now and school.plan == plan_id) else now
    end = start + timedelta(days=period_days)

    school.plan = plan_id
    school.plan_valid_until = _naive(end)
    if offer is not None:
        school.custom_limits = {
            "max_sections": offer.max_sections,
            "max_members": offer.max_members,
            "max_owned_schools": offer.max_owned_schools,
        }
        school.custom_plan_name = offer.name
        offer.status = "paid"
        offer.paid_at = _naive(now)
    elif plan_id != "business":
        school.custom_limits = None
        school.custom_plan_name = None
    return _naive(start), _naive(end)


def _billed_to(school: School) -> dict:
    p = school.profile or {}
    lines = [p.get("address"), ", ".join(x for x in [p.get("city"), p.get("state"), p.get("postal_code")] if x), p.get("country")]
    return {
        "name": school.name,
        "address": [line for line in lines if line],
        "email": p.get("email"),
        "phone": p.get("phone"),
    }


def _next_number(db: Session, year: int) -> str:
    prefix = f"TZ-{year}-"
    last = (
        db.query(Invoice.number)
        .filter(Invoice.number.like(f"{prefix}%"))
        .order_by(Invoice.number.desc())
        .first()
    )
    seq = int(last[0].rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{seq:04d}"


def issue_invoice(
    db: Session,
    school: School,
    *,
    description: str,
    amount_paise: int,
    method: str,
    reference: str | None = None,
    payment_order_id: int | None = None,
    period: tuple[datetime, datetime] | None = None,
) -> Invoice:
    """Create and commit the next numbered invoice. Retries once if two
    payments race for the same number (the column is unique)."""
    now = datetime.now(timezone.utc)
    for attempt in range(2):
        invoice = Invoice(
            number=_next_number(db, now.year),
            school_id=school.id,
            payment_order_id=payment_order_id,
            description=description[:200],
            amount_paise=amount_paise,
            currency="INR",
            method=method,
            reference=(reference or None) and reference[:100],
            billed_to=_billed_to(school),
            period_start=period[0] if period else None,
            period_end=period[1] if period else None,
            issued_at=_naive(now),
        )
        db.add(invoice)
        try:
            db.commit()
            return invoice
        except IntegrityError:
            db.rollback()
            if attempt:
                raise
    raise RuntimeError("unreachable")


def plan_label(plan_id: str, offer: PlanOffer | None = None) -> str:
    if offer is not None:
        return offer.name
    return {"pro": "Timetablz Pro", "business": "Timetablz Business"}.get(plan_id, plan_id.title())


# ---------------------------------------------------------------------------
# Invoice PDF - same neutral look as the timetable exports.
# ---------------------------------------------------------------------------

_INK = colors.HexColor("#171717")
_MUTED = colors.HexColor("#737373")
_LINE = colors.HexColor("#E5E5E5")


def _date(dt: datetime | None) -> str:
    return dt.strftime("%d %b %Y").lstrip("0") if dt else ""


def invoice_pdf(invoice: Invoice) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                            title=f"Invoice {invoice.number}", author="Timetablz")
    # DejaVu isn't bundled with reportlab; Helvetica has no ₹ glyph, so amounts
    # are written as "Rs." in the PDF.
    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=_INK)
    small = ParagraphStyle("s", fontName="Helvetica", fontSize=9, leading=13, textColor=_MUTED)
    body = ParagraphStyle("b", fontName="Helvetica", fontSize=10, leading=14, textColor=_INK)
    bold = ParagraphStyle("bb", parent=body, fontName="Helvetica-Bold")

    def esc(t):
        return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def rs(paise):
        return f"Rs. {paise / 100:,.2f}"

    bt = invoice.billed_to or {}
    seller = [esc(settings.invoice_seller_name), esc(settings.invoice_seller_address), esc(settings.invoice_seller_email)]
    if settings.invoice_seller_gstin:
        seller.append(f"GSTIN: {esc(settings.invoice_seller_gstin)}")
    billed = [f"<b>{esc(bt.get('name'))}</b>"] + [esc(x) for x in bt.get("address", [])]
    for extra in (bt.get("email"), bt.get("phone")):
        if extra:
            billed.append(esc(extra))

    story = [
        Table(
            [[Paragraph("Timetablz", ParagraphStyle("brand", parent=bold, fontSize=13)), Paragraph("INVOICE", ParagraphStyle("t", parent=bold, alignment=2, textColor=_MUTED))]],
            colWidths=[8.25 * cm, 8.25 * cm], hAlign="LEFT",
            style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]),
        ),
        Spacer(1, 0.6 * cm),
        Paragraph(esc(invoice.number), h1),
        Paragraph(f"Issued {_date(invoice.issued_at)}", small),
        Spacer(1, 0.8 * cm),
        Table(
            [
                [Paragraph("FROM", small), Paragraph("BILLED TO", small)],
                [Paragraph("<br/>".join(seller), body), Paragraph("<br/>".join(billed), body)],
            ],
            colWidths=[8.25 * cm, 8.25 * cm], hAlign="LEFT",
            style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, 0), 4)]),
        ),
        Spacer(1, 1 * cm),
    ]

    period = ""
    if invoice.period_start and invoice.period_end:
        period = f"<br/><font color='#737373' size='9'>Service period {_date(invoice.period_start)} to {_date(invoice.period_end)}</font>"
    lines = Table(
        [
            [Paragraph("<b>Description</b>", body), Paragraph("<b>Amount</b>", ParagraphStyle("r", parent=body, alignment=2))],
            [Paragraph(esc(invoice.description) + period, body), Paragraph(rs(invoice.amount_paise), ParagraphStyle("r2", parent=body, alignment=2))],
            [Paragraph("<b>Total</b>", body), Paragraph(f"<b>{rs(invoice.amount_paise)}</b>", ParagraphStyle("r3", parent=body, alignment=2))],
        ],
        colWidths=[12 * cm, 4.5 * cm], hAlign="LEFT",
        style=TableStyle([
            ("LINEBELOW", (0, 0), (-1, 0), 0.75, _INK),
            ("LINEBELOW", (0, 1), (-1, 1), 0.5, _LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]),
    )
    story.append(lines)
    story.append(Spacer(1, 0.8 * cm))

    method = {"online": "Paid online via Cashfree Payments", "bank_transfer": "Paid by bank transfer"}.get(invoice.method, "Paid")
    paid_line = method + (f" (ref. {esc(invoice.reference)})" if invoice.reference else "")
    story.append(Paragraph(paid_line, body))
    if not settings.invoice_seller_gstin:
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph("The supplier is not registered under GST, so no GST has been charged.", small))
    story.append(Spacer(1, 1.2 * cm))
    story.append(Paragraph("Thank you for using Timetablz. Questions about this invoice: support@timetablz.com", small))

    doc.build(story)
    return buf.getvalue()
