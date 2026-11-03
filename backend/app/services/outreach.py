"""
Timetablz's sales outreach: the school list, finding who to write to,
drafting emails, sending them slowly from a Gmail mailbox, and noticing
replies. Run from the admin page (app/routers/outreach.py).

How an email gets out:

  1. A school is on the list (imported from the outreach workbook, or added).
  2. "Find contacts" reads the school's own website for the principal's name.
  3. "Draft" writes a three-email sequence from the templates, with a line
     about that school. Nothing is sent from a draft.
  4. Someone reads it and approves it.
  5. The background sender (run_cycle) sends approved emails one at a time,
     inside school hours, a few minutes apart, never more than the day's
     limit - which starts low and rises over the first fortnight, because a
     mailbox that suddenly sends a lot looks like spam.
  6. Follow-ups wait a few days after the email before them and go in the
     same thread. A reply, a bounce or an opt-out stops the sequence.

Sending is through Gmail's HTTPS API, not SMTP: Railway blocks outbound SMTP
on its lower plans. Tests swap the provider out (set_provider).
"""
from __future__ import annotations

import base64
import html
import io
import logging
import random
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings as app_settings
from app.models.outreach import OutreachMessage, OutreachSchool, OutreachSettings

log = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
# Monday-Saturday, 9:30 to 4:30 India time: when a school office reads email.
SEND_DAYS = {0, 1, 2, 3, 4, 5}
SEND_START = (9, 30)
SEND_END = (16, 30)
# However the limit is set, a mailbox on the company's main domain never
# sends more than this in a day.
HARD_DAILY_CAP = 40
# Minutes between two emails, picked at random in this range.
GAP_MINUTES = (6, 14)

STOP_WORDS = re.compile(
    r"\b(unsubscribe|remove me|stop|not interested|no thanks|don'?t (email|contact|write)|do not (email|contact|write))\b",
    re.I,
)
# Statuses where a school is not written to any more.
CLOSED = {"replied", "bounced", "opted_out", "demo_booked", "trial", "paid", "not_interested"}

DEFAULT_SENDER = "Arpith David"
DEFAULT_SIGNATURE = "Arpith David\nTimetablz - timetables for schools\ntimetablz.com | Chennai"
DEFAULT_FOLLOW_UPS = [4, 6]
DEFAULT_TEMPLATES = {
    "1": {
        "subject": "Timetables at {school}",
        "body": (
            "Dear {greeting},\n\n"
            "{personal_line}\n\n"
            "I'm {sender_first}, and I run Timetablz, a timetable tool made in Chennai for schools like "
            "{school}. You enter your classes, subjects and teachers, write your rules the way you would "
            "say them (\"Maths in the first half of the day\", \"Mrs. Rao is off on Saturdays\"), and it "
            "builds a clash-free timetable for every section and every teacher in minutes. Electives, "
            "labs and substitutions are handled too.\n\n"
            "Would a 15-minute look be useful? I'm happy to build {school}'s first timetable for you, "
            "free, so you can judge it on your own data.\n\n"
            "{signature}\n\n"
            "If this isn't relevant, just reply \"no\" and I won't write again."
        ),
    },
    "2": {
        "subject": "Re: Timetables at {school}",
        "body": (
            "Dear {greeting},\n\n"
            "Just bringing this back to the top of your inbox. If next year's timetable is on your list, "
            "I can show you how {school}'s week would come out in a short call, or build it straight from "
            "your current timetable.\n\n"
            "{signature}"
        ),
    },
    "3": {
        "subject": "Re: Timetables at {school}",
        "body": (
            "Dear {greeting},\n\n"
            "I'll leave it here. If timetables or substitutions become a headache later in the year, "
            "my details are below and I'd be glad to help.\n\n"
            "Wishing {school} a good term.\n\n"
            "{signature}"
        ),
    },
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def get_settings(db: Session) -> OutreachSettings:
    row = db.get(OutreachSettings, 1)
    if row is None:
        row = OutreachSettings(
            id=1, sender_name=DEFAULT_SENDER, signature=DEFAULT_SIGNATURE,
            templates=DEFAULT_TEMPLATES, daily_limit=15, follow_up_days=DEFAULT_FOLLOW_UPS,
            sending_enabled=False,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def templates_of(row: OutreachSettings) -> dict:
    out = {k: dict(v) for k, v in DEFAULT_TEMPLATES.items()}
    for k, v in (row.templates or {}).items():
        if k in out and isinstance(v, dict):
            out[k].update({f: v[f] for f in ("subject", "body") if isinstance(v.get(f), str)})
    return out


def effective_daily_limit(row: OutreachSettings, now: datetime | None = None) -> int:
    """The day's limit, held down while the mailbox is new to sending."""
    limit = max(0, min(row.daily_limit or 0, HARD_DAILY_CAP))
    first = _aware(row.first_sent_at)
    if first is None:
        return min(limit, 10)
    days = ((now or _now()) - first).days
    if days < 7:
        return min(limit, 10)
    if days < 14:
        return min(limit, 20)
    return limit


def in_send_window(now: datetime | None = None) -> bool:
    local = (now or _now()).astimezone(IST)
    if local.weekday() not in SEND_DAYS:
        return False
    hm = (local.hour, local.minute)
    return SEND_START <= hm < SEND_END


def sent_today(db: Session, now: datetime | None = None) -> int:
    local = (now or _now()).astimezone(IST)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    return db.query(OutreachMessage).filter(
        OutreachMessage.status == "sent", OutreachMessage.sent_at >= start,
    ).count()


# ---------------------------------------------------------------------------
# Importing the workbook
# ---------------------------------------------------------------------------

_COLUMNS = {
    "name": ("school",),
    "district": ("district",),
    "group_name": ("group / chain", "group"),
    "board": ("board",),
    "classes_up_to": ("classes up to",),
    "school_type": ("type",),
    "priority": ("priority",),
    "website": ("website",),
    "emails": ("email (school website)", "email"),
    "email_source": ("email source / note", "email source"),
    "area": ("area (fill in)", "area"),
    "phone": ("phone (fill in)", "phone"),
    "contact_name": ("timetable in-charge (fill in)", "timetable in-charge"),
    "notes": ("notes",),
}
_SHEET_DISTRICT = {"cbse schools": "Chennai", "icse schools": "Chennai"}
_STATUS_FROM_SHEET = {
    "demo booked": "demo_booked", "trial": "trial", "paid": "paid", "not interested": "not_interested",
}


def _split_emails(value) -> list[str]:
    if not value:
        return []
    found = re.findall(r"[\w.%+-]+@[\w-]+(?:\.[\w-]+)+", str(value))
    return list(dict.fromkeys(e.lower() for e in found))


def import_workbook(db: Session, data: bytes) -> dict:
    """Add the workbook's schools, or bring existing ones up to date.

    A school already on the list keeps its status, notes and anything found
    since; only facts from the sheet (website, board, emails...) fill in what
    is missing.
    """
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    existing = {
        (s.name.strip().lower(), (s.district or "").strip().lower()): s
        for s in db.query(OutreachSchool).all()
    }
    added = updated = 0
    for ws in wb.worksheets:
        rows = ws.iter_rows(values_only=True)
        header = next(rows, None)
        if not header:
            continue
        names = [str(h or "").strip().lower() for h in header]
        if "school" not in names:
            continue
        col = {
            field: next((names.index(a) for a in aliases if a in names), None)
            for field, aliases in _COLUMNS.items()
        }
        status_col = names.index("status") if "status" in names else None
        default_district = _SHEET_DISTRICT.get(ws.title.strip().lower())
        for r in rows:
            def val(field):
                i = col.get(field)
                v = r[i] if i is not None and i < len(r) else None
                return str(v).strip() if v not in (None, "") else None

            name = val("name")
            if not name:
                continue
            district = val("district") or default_district
            key = (name.lower(), (district or "").lower())
            facts = {
                "district": district, "group_name": val("group_name"), "board": val("board"),
                "classes_up_to": val("classes_up_to"), "school_type": val("school_type"),
                "priority": val("priority"), "website": val("website"),
                "email_source": val("email_source"), "area": val("area"), "phone": val("phone"),
                "contact_name": val("contact_name"), "notes": val("notes"),
            }
            emails = _split_emails(val("emails"))
            sheet_status = None
            if status_col is not None and status_col < len(r) and r[status_col]:
                sheet_status = _STATUS_FROM_SHEET.get(str(r[status_col]).strip().lower())
            school = existing.get(key)
            if school is None:
                school = OutreachSchool(name=name, emails=emails or None, status=sheet_status or "not_contacted",
                                        **{k: v for k, v in facts.items() if v})
                db.add(school)
                existing[key] = school
                added += 1
            else:
                changed = False
                for k, v in facts.items():
                    if v and not getattr(school, k):
                        setattr(school, k, v)
                        changed = True
                merged = list(dict.fromkeys([*(school.emails or []), *emails]))
                if merged != (school.emails or []):
                    school.emails = merged
                    changed = True
                updated += int(changed)
    db.commit()
    return {"added": added, "updated": updated, "total": db.query(OutreachSchool).count()}


# ---------------------------------------------------------------------------
# Finding the people
# ---------------------------------------------------------------------------

_TITLE = r"(?:Dr|Mr|Mrs|Ms|Miss|Smt|Shri|Sri|Fr|Sr|Rev|Prof)\.?"
_NAME = r"[A-Z][A-Za-z.']+(?:\s+[A-Z][A-Za-z.']*){0,4}"
_ROLE_WORDS = ("principal", "vice", "coordinator", "headmistress", "headmaster", "correspondent",
               "director", "chairman", "secretary", "email", "phone", "contact", "mobile", "school",
               "message", "desk", "about", "read", "more", "the", "our", "and", "of")
_PRINCIPAL_PATTERNS = [
    re.compile(rf"Name of (?:the )?(?:Principal|Head of (?:the )?(?:School|Institution))[^A-Za-z]{{0,12}}((?:{_TITLE}\s*)?{_NAME})"),
    re.compile(rf"\b(?:Principal|PRINCIPAL)\b\s*(?:Name)?\s*[:\-–\u2014|]\s*((?:{_TITLE}\s*)?{_NAME})"),
    re.compile(rf"\b(?:Principal|PRINCIPAL)\b[ \t]*\n\s*({_TITLE}\s*{_NAME})"),
    re.compile(rf"({_TITLE}\s*{_NAME})\s*[,\-–\u2014(|\n]{{0,3}}\s*(?:M\.?\w*\.?,?\s*(?:B\.?\s?Ed\.?)?\s*)?[,\-–\u2014(|\n]{{0,3}}\s*(?:The\s+)?Principal\b"),
]
_OTHER_ROLES = ("Vice Principal", "Academic Coordinator", "Headmistress", "Head Mistress", "Headmaster", "Correspondent")


def _page_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", "\n", raw)
    text = html.unescape(raw)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text)


def _clean_name(candidate: str) -> str | None:
    words = candidate.replace("\n", " ").split()
    kept = []
    for w in words:
        if w.lower().strip(".,:") in _ROLE_WORDS and kept and not re.fullmatch(_TITLE, w):
            break
        kept.append(w)
    name = " ".join(kept).strip(" .,-:")
    plain = [w for w in name.split() if not re.fullmatch(_TITLE, w)]
    if not (1 <= len(plain) <= 5) or any(len(w) > 20 for w in plain):
        return None
    if all(len(w.strip(".")) <= 1 for w in plain):
        return None
    if any(w.lower().strip(".,") in _ROLE_WORDS for w in plain):
        return None
    return name


def extract_people(text: str) -> dict:
    """The principal and one other useful contact named in a page's text."""
    out = {}
    for pattern in _PRINCIPAL_PATTERNS:
        m = pattern.search(text)
        if m:
            name = _clean_name(m.group(1))
            if name:
                out["principal_name"] = name
                break
    for role in _OTHER_ROLES:
        m = re.search(rf"\b{role}\b\s*[:\-–\u2014|]\s*((?:{_TITLE}\s*)?{_NAME})", text, re.I) or re.search(
            rf"\b{role}\b[ \t]*\n\s*({_TITLE}\s*{_NAME})", text, re.I) or re.search(
            rf"({_TITLE}\s*{_NAME})\s*[,\-–\u2014(|\n]{{0,3}}\s*(?:The\s+)?{role}\b", text)
        if m:
            name = _clean_name(m.group(1))
            if name and name != out.get("principal_name"):
                out["contact_name"] = name
                out["contact_role"] = role.replace("Head Mistress", "Headmistress")
                break
    emails = _split_emails(text)
    if emails:
        out["emails"] = [e for e in emails if not re.search(r"\.(png|jpe?g|gif|svg|webp)$|@(example\.com|domain\.com|email\.com)$|sentry|wix", e)]
    return out


_LINK_HINTS = re.compile(r"disclosure|mandatory|principal|about|leadership|management|administration|contact|faculty|staff", re.I)


def _candidate_links(base: str, raw: str) -> list[str]:
    host = urlparse(base).netloc.replace("www.", "")
    links = []
    for href, label in re.findall(r"(?is)<a[^>]+href=[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>", raw):
        if not _LINK_HINTS.search(href + " " + re.sub(r"<[^>]+>", "", label)):
            continue
        url = urljoin(base, href.strip())
        if urlparse(url).netloc.replace("www.", "") != host or url.lower().endswith((".jpg", ".png", ".zip")):
            continue
        links.append(url)
    # Disclosure and principal pages first: they are where the name usually is.
    links.sort(key=lambda u: 0 if re.search(r"disclosure|mandatory|principal", u, re.I) else 1)
    return list(dict.fromkeys(links))[:5]


def find_contacts_for(website: str, fetch=None) -> dict:
    """Read a school's own website for its principal and another contact.

    Looks at the home page and up to five likely pages from it: the CBSE
    mandatory disclosure, the principal's page, about, contact. Returns what
    it found and the page it was found on.
    """
    if not website:
        return {}
    url = website if website.startswith("http") else f"https://{website}"
    fetch = fetch or _fetch
    found: dict = {}
    raw = fetch(url)
    if raw is None:
        return {"error": "The website didn't load."}
    pages = [(url, raw)]
    for link in _candidate_links(url, raw):
        page = fetch(link)
        if page is not None:
            pages.append((link, page))
    for page_url, page_raw in pages:
        people = extract_people(_page_text(page_raw))
        for key in ("principal_name", "contact_name", "contact_role"):
            if people.get(key) and not found.get(key):
                found[key] = people[key]
                if key == "principal_name":
                    found["source"] = page_url
        if people.get("emails"):
            found.setdefault("emails", [])
            found["emails"] = list(dict.fromkeys([*found["emails"], *people["emails"]]))
        if found.get("principal_name") and found.get("contact_name"):
            break
    if not found.get("source") and found.get("contact_name"):
        found["source"] = pages[0][0]
    return found


def _fetch(url: str) -> str | None:
    try:
        r = httpx.get(url, timeout=12, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (compatible; Timetablz outreach; +https://timetablz.com)",
        })
        if r.status_code >= 400 or "html" not in r.headers.get("content-type", "html"):
            return None
        return r.text[:600_000]
    except Exception:  # noqa: BLE001 - a dead website is an ordinary outcome
        return None


# One background job at a time, for the dashboard to watch.
JOB: dict = {"running": False}
_JOB_LOCK = threading.Lock()


def start_find_contacts(school_ids: list[int], session_factory, fetch=None, background=True) -> dict:
    with _JOB_LOCK:
        if JOB.get("running"):
            return JOB
        JOB.clear()
        JOB.update({"running": True, "kind": "find_contacts", "total": len(school_ids), "done": 0,
                    "found": 0, "started_at": _now().isoformat()})

    def work():
        db = session_factory()
        try:
            for sid in school_ids:
                school = db.get(OutreachSchool, sid)
                if school is not None and school.website:
                    result = find_contacts_for(school.website, fetch=fetch)
                    if result.get("principal_name"):
                        school.principal_name = result["principal_name"]
                        JOB["found"] += 1
                    if result.get("contact_name"):
                        school.contact_name = result["contact_name"]
                        school.contact_role = result.get("contact_role")
                    if result.get("source"):
                        school.contact_source = result["source"]
                    if result.get("emails"):
                        school.emails = list(dict.fromkeys([*(school.emails or []), *result["emails"]]))[:6]
                    school.contacts_checked_at = _now()
                    db.commit()
                JOB["done"] += 1
        finally:
            db.close()
            JOB["running"] = False
            JOB["finished_at"] = _now().isoformat()

    if background:
        threading.Thread(target=work, daemon=True).start()
    else:
        work()
    return JOB


# ---------------------------------------------------------------------------
# Drafting
# ---------------------------------------------------------------------------


def greeting_for(school: OutreachSchool) -> str:
    name = (school.principal_name or "").strip()
    if not name:
        return "Principal"
    words = name.replace(",", " ").split()
    title = words[0].rstrip(".") if re.fullmatch(_TITLE, words[0]) else None
    rest = [w for w in words[1:] if len(w.strip(".")) > 1] if title else words
    if title and rest:
        return f"{title}. {rest[-1]}"
    return name


def personal_line(school: OutreachSchool, group_sizes: dict[str, int]) -> str:
    group = school.group_name
    if group and group_sizes.get(group, 0) > 1 and "Kendriya" not in group:
        return (
            f"As {school.name} is one of several {group} campuses, I imagine timetables are planned "
            f"across schools each year, which is where most of the time goes."
        )
    classes = (school.classes_up_to or "").lower()
    where = f" in {school.area}" if school.area else ""
    if "12" in classes:
        return (
            f"With classes up to 12 at {school.name}{where}, I imagine the senior timetable, with its "
            f"streams and electives, takes the longest to put together each year."
        )
    if "10" in classes:
        return (
            f"Putting together a clash-free timetable for every section up to Class 10 at "
            f"{school.name}{where} usually takes someone several days each year."
        )
    return (
        f"Building a clash-free timetable for every section and teacher at {school.name}{where} "
        f"usually takes someone days of work each year, and again whenever a teacher changes."
    )


def render(template: dict, school: OutreachSchool, row: OutreachSettings, group_sizes: dict[str, int]) -> tuple[str, str]:
    sender = (row.sender_name or DEFAULT_SENDER).strip()
    values = {
        "school": school.name,
        "greeting": greeting_for(school),
        "personal_line": personal_line(school, group_sizes),
        "sender_name": sender,
        "sender_first": sender.split()[0] if sender else "",
        "signature": (row.signature or DEFAULT_SIGNATURE).strip(),
        "area": school.area or school.district or "Chennai",
    }

    def fill(text: str) -> str:
        return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), text)

    return fill(template["subject"]), fill(template["body"])


def draftable(school: OutreachSchool) -> bool:
    return bool(school.recipient) and school.status not in CLOSED


def create_drafts(db: Session, school_ids: list[int]) -> dict:
    """Write the three-email sequence for each school that doesn't have one.

    A school already in a sequence (any email not cancelled), with nowhere to
    send to, or closed (replied, opted out...) is skipped.
    """
    row = get_settings(db)
    templates = templates_of(row)
    group_sizes: dict[str, int] = {}
    for (g,) in db.query(OutreachSchool.group_name).filter(OutreachSchool.group_name.isnot(None)):
        group_sizes[g] = group_sizes.get(g, 0) + 1
    created = skipped = 0
    for school in db.query(OutreachSchool).filter(OutreachSchool.id.in_(school_ids)).all():
        live = db.query(OutreachMessage).filter(
            OutreachMessage.school_id == school.id, OutreachMessage.status != "cancelled",
        ).count()
        if live or not draftable(school):
            skipped += 1
            continue
        for step in (1, 2, 3):
            subject, body = render(templates[str(step)], school, row, group_sizes)
            db.add(OutreachMessage(school_id=school.id, step=step, to_email=school.recipient,
                                   subject=subject, body=body, status="draft"))
        created += 1
    db.commit()
    return {"created": created, "skipped": skipped}


def approve(db: Session, school_ids: list[int]) -> int:
    now = _now()
    n = 0
    for m in db.query(OutreachMessage).filter(
        OutreachMessage.school_id.in_(school_ids), OutreachMessage.status == "draft",
    ).all():
        m.status = "approved"
        m.approved_at = now
        n += 1
    db.commit()
    return n


def cancel(db: Session, school_ids: list[int], reason: str | None = None) -> int:
    n = 0
    for m in db.query(OutreachMessage).filter(
        OutreachMessage.school_id.in_(school_ids), OutreachMessage.status.in_(("draft", "approved")),
    ).all():
        m.status = "cancelled"
        if reason:
            m.error = reason
        n += 1
    db.commit()
    return n


# ---------------------------------------------------------------------------
# Gmail
# ---------------------------------------------------------------------------

GMAIL_SCOPES = "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly"


class MailboxError(Exception):
    pass


class GmailProvider:
    """Sends and reads through the Gmail API with an OAuth refresh token."""

    def __init__(self, refresh_token: str, address: str | None):
        self.refresh_token = refresh_token
        self.address = address
        self._token = None
        self._expires = 0.0

    def _access(self) -> str:
        if self._token and time.time() < self._expires - 60:
            return self._token
        r = httpx.post("https://oauth2.googleapis.com/token", data={
            "client_id": app_settings.outreach_google_client_id,
            "client_secret": app_settings.outreach_google_client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }, timeout=20)
        if r.status_code != 200:
            raise MailboxError(f"Gmail sign-in failed ({r.status_code}). Connect the mailbox again.")
        body = r.json()
        self._token = body["access_token"]
        self._expires = time.time() + int(body.get("expires_in", 3000))
        return self._token

    def _api(self, method: str, path: str, **kw):
        r = httpx.request(method, f"https://gmail.googleapis.com/gmail/v1/users/me/{path}",
                          headers={"Authorization": f"Bearer {self._access()}"}, timeout=30, **kw)
        if r.status_code >= 400:
            raise MailboxError(f"Gmail said {r.status_code}: {r.text[:300]}")
        return r.json()

    def send(self, to: str, subject: str, body: str, from_name: str,
             thread_id: str | None = None, in_reply_to: str | None = None) -> dict:
        msg = EmailMessage()
        msg["To"] = to
        msg["From"] = formataddr((from_name, self.address)) if self.address else from_name
        msg["Subject"] = subject
        rfc_id = make_msgid(domain=(self.address or "timetablz.com").split("@")[-1])
        msg["Message-ID"] = rfc_id
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        msg.set_content(body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        payload = {"raw": raw}
        if thread_id:
            payload["threadId"] = thread_id
        sent = self._api("POST", "messages/send", json=payload)
        return {"id": sent.get("id"), "thread_id": sent.get("threadId"), "rfc_message_id": rfc_id}

    def thread_replies(self, thread_id: str) -> list[dict]:
        """Messages in a thread not sent by this mailbox: [{from, snippet}]."""
        data = self._api("GET", f"threads/{thread_id}", params={
            "format": "metadata", "metadataHeaders": ["From"],
        })
        out = []
        for m in data.get("messages", []):
            headers = {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}
            sender = headers.get("from", "")
            if self.address and self.address.lower() in sender.lower():
                continue
            out.append({"from": sender, "snippet": html.unescape(m.get("snippet", ""))})
        return out


# ---------------------------------------------------------------------------
# Zoho Mail
# ---------------------------------------------------------------------------
#
# Zoho's Mail REST API (https://www.zoho.com/mail/help/api/) over HTTPS, the
# same way as Gmail. Two differences shape the code:
#   - A follow-up goes out with Zoho's "reply" action on the first email's
#     message id, which keeps it in the same thread for the school.
#   - There is no "give me this thread" call, so replies are found by
#     searching the inbox for mail from the school's address since the first
#     email, and bounces by searching mailer-daemon mail that names it. The
#     "thread id" stored on a sent message is that search: "address|date".

ZOHO_SCOPES = "ZohoMail.messages.ALL,ZohoMail.accounts.READ"


def _zoho_accounts_for(api_domain: str | None) -> str:
    """mail.zoho.in -> https://accounts.zoho.in: tokens are refreshed at the
    data centre the mailbox lives in."""
    if api_domain and "mail.zoho." in api_domain:
        return "https://accounts.zoho." + api_domain.split("mail.zoho.", 1)[1].strip("/")
    return app_settings.outreach_zoho_accounts_url.rstrip("/")


def _zoho_mail_for(accounts_url: str) -> str:
    """https://accounts.zoho.in -> mail.zoho.in"""
    host = accounts_url.split("//", 1)[-1].strip("/")
    return host.replace("accounts.", "mail.", 1) if host.startswith("accounts.") else "mail.zoho.in"


class ZohoProvider:
    def __init__(self, refresh_token: str, address: str | None, account_id: str, api_domain: str):
        self.refresh_token = refresh_token
        self.address = address
        self.account_id = account_id
        self.api_domain = api_domain
        self._token = None
        self._expires = 0.0

    def _access(self) -> str:
        if self._token and time.time() < self._expires - 60:
            return self._token
        r = httpx.post(f"{_zoho_accounts_for(self.api_domain)}/oauth/v2/token", data={
            "client_id": app_settings.outreach_zoho_client_id,
            "client_secret": app_settings.outreach_zoho_client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }, timeout=20)
        body = r.json() if r.status_code == 200 else {}
        if not body.get("access_token"):
            raise MailboxError(f"Zoho sign-in failed ({r.status_code}). Connect the mailbox again.")
        self._token = body["access_token"]
        self._expires = time.time() + int(body.get("expires_in", 3000))
        return self._token

    def _api(self, method: str, path: str, **kw):
        r = httpx.request(method, f"https://{self.api_domain}/api/accounts/{self.account_id}/{path}",
                          headers={"Authorization": f"Zoho-oauthtoken {self._access()}"}, timeout=30, **kw)
        if r.status_code >= 400:
            raise MailboxError(f"Zoho said {r.status_code}: {r.text[:300]}")
        return r.json().get("data")

    def send(self, to: str, subject: str, body: str, from_name: str,
             thread_id: str | None = None, in_reply_to: str | None = None) -> dict:
        payload = {"fromAddress": self.address, "toAddress": to, "subject": subject,
                   "content": body, "mailFormat": "plaintext"}
        data = None
        original = in_reply_to  # for Zoho, the first email's Zoho message id
        if original:
            try:
                data = self._api("POST", f"messages/{original}", json={**payload, "action": "reply"})
            except MailboxError:
                data = None  # the first email is gone from Sent - send it as a new email
        if data is None:
            data = self._api("POST", "messages", json=payload)
        data = data or {}
        message_id = str(data.get("messageId") or "") or None
        key = thread_id or f"{to}|{_now().astimezone(IST):%d-%b-%Y}"
        # Follow-ups reply to the first email, so that's the id they need.
        return {"id": message_id, "thread_id": key, "rfc_message_id": original or message_id}

    def _search(self, key: str) -> list[dict]:
        return self._api("GET", "messages/search", params={"searchKey": key, "limit": 20}) or []

    def thread_replies(self, thread_id: str) -> list[dict]:
        address, _, since = thread_id.partition("|")
        since = f"::fromDate:{since}" if since else ""
        out = []
        for m in self._search(f"sender:{address}{since}"):
            out.append({"from": m.get("fromAddress") or m.get("sender") or "",
                        "snippet": html.unescape(m.get("summary") or m.get("subject") or "")})
        for m in self._search(f"sender:mailer-daemon::entire:{address}{since}"):
            out.append({"from": m.get("fromAddress") or "mailer-daemon", "snippet": m.get("summary") or ""})
        return out


def zoho_configured() -> bool:
    return bool(app_settings.outreach_zoho_client_id and app_settings.outreach_zoho_client_secret)


def zoho_auth_url(state: str) -> str:
    from urllib.parse import urlencode
    return f"{app_settings.outreach_zoho_accounts_url.rstrip('/')}/oauth/v2/auth?" + urlencode({
        "scope": ZOHO_SCOPES, "client_id": app_settings.outreach_zoho_client_id,
        "response_type": "code", "access_type": "offline", "prompt": "consent",
        "redirect_uri": app_settings.outreach_zoho_redirect_uri, "state": state,
    })


def exchange_zoho_code(code: str, accounts_server: str | None = None) -> dict:
    """Finish connecting a Zoho mailbox: refresh token, address, account id
    and the mail API host of its data centre."""
    accounts = (accounts_server or app_settings.outreach_zoho_accounts_url).rstrip("/")
    if not re.fullmatch(r"https://accounts\.zoho\.[a-z.]+", accounts):
        raise MailboxError("Zoho sent the sign-in back from an unexpected address.")
    r = httpx.post(f"{accounts}/oauth/v2/token", data={
        "code": code,
        "client_id": app_settings.outreach_zoho_client_id,
        "client_secret": app_settings.outreach_zoho_client_secret,
        "redirect_uri": app_settings.outreach_zoho_redirect_uri,
        "grant_type": "authorization_code",
    }, timeout=20)
    tokens = r.json() if r.status_code == 200 else {}
    if not tokens.get("access_token"):
        raise MailboxError(f"Zoho refused the connection ({tokens.get('error') or r.status_code}).")
    if not tokens.get("refresh_token"):
        raise MailboxError("Zoho didn't return a long-lived token. Connect again.")
    api_domain = _zoho_mail_for(accounts)
    acc = httpx.get(f"https://{api_domain}/api/accounts",
                    headers={"Authorization": f"Zoho-oauthtoken {tokens['access_token']}"}, timeout=20)
    accounts_list = (acc.json().get("data") or []) if acc.status_code == 200 else []
    if not accounts_list:
        raise MailboxError("Connected to Zoho, but couldn't find a mail account on it.")
    a = accounts_list[0]
    address = a.get("primaryEmailAddress") or a.get("mailboxAddress") or (
        (a.get("emailAddress") or [{}])[0].get("mailId") if isinstance(a.get("emailAddress"), list) else None)
    return {"refresh_token": tokens["refresh_token"], "address": address,
            "account_id": str(a.get("accountId")), "api_domain": api_domain}


_PROVIDER_OVERRIDE = None


def set_provider(provider) -> None:
    """For tests: send through this object instead of a real mailbox."""
    global _PROVIDER_OVERRIDE
    _PROVIDER_OVERRIDE = provider


def provider_for(row: OutreachSettings):
    if _PROVIDER_OVERRIDE is not None:
        return _PROVIDER_OVERRIDE
    if not row.gmail_refresh_token:
        return None
    if row.mailbox_provider == "zoho":
        return ZohoProvider(row.gmail_refresh_token, row.gmail_address, row.zoho_account_id, row.zoho_api_domain)
    return GmailProvider(row.gmail_refresh_token, row.gmail_address)


def gmail_configured() -> bool:
    return bool(app_settings.outreach_google_client_id and app_settings.outreach_google_client_secret)


def exchange_code(code: str) -> dict:
    """Finish connecting a mailbox: the refresh token and its address."""
    r = httpx.post("https://oauth2.googleapis.com/token", data={
        "code": code,
        "client_id": app_settings.outreach_google_client_id,
        "client_secret": app_settings.outreach_google_client_secret,
        "redirect_uri": app_settings.outreach_google_redirect_uri,
        "grant_type": "authorization_code",
    }, timeout=20)
    if r.status_code != 200:
        raise MailboxError(f"Google refused the connection ({r.status_code}).")
    tokens = r.json()
    if not tokens.get("refresh_token"):
        raise MailboxError("Google didn't return a long-lived token. Remove Timetablz's access in your "
                           "Google account and connect again.")
    profile = httpx.get("https://gmail.googleapis.com/gmail/v1/users/me/profile",
                        headers={"Authorization": f"Bearer {tokens['access_token']}"}, timeout=20)
    address = profile.json().get("emailAddress") if profile.status_code == 200 else None
    return {"refresh_token": tokens["refresh_token"], "address": address}


# ---------------------------------------------------------------------------
# Sending and replies
# ---------------------------------------------------------------------------

_STATE = {"next_send_at": None}


def next_due(db: Session, now: datetime) -> OutreachMessage | None:
    """The next approved email that may go now: follow-ups that are due
    first (they are on a clock), then first emails in the order approved."""
    candidates = (
        db.query(OutreachMessage).join(OutreachSchool, OutreachSchool.id == OutreachMessage.school_id)
        .filter(OutreachMessage.status == "approved", ~OutreachSchool.status.in_(CLOSED))
        .order_by(OutreachMessage.step.desc(), OutreachMessage.approved_at, OutreachMessage.id)
        .all()
    )
    for m in candidates:
        if m.step == 1:
            return m
        due = _aware(m.not_before)
        if due is not None and due <= now:
            return m
    return None


def send_one(db: Session, row: OutreachSettings, provider, now: datetime | None = None) -> OutreachMessage | None:
    now = now or _now()
    message = next_due(db, now)
    if message is None:
        return None
    school = db.get(OutreachSchool, message.school_id)
    previous = None
    if message.step > 1:
        previous = db.query(OutreachMessage).filter(
            OutreachMessage.school_id == message.school_id, OutreachMessage.step == message.step - 1,
            OutreachMessage.status == "sent",
        ).first()
    try:
        result = provider.send(
            to=message.to_email, subject=message.subject, body=message.body,
            from_name=(row.sender_name or DEFAULT_SENDER),
            thread_id=previous.provider_thread_id if previous else None,
            in_reply_to=previous.rfc_message_id if previous else None,
        )
    except Exception as e:  # noqa: BLE001 - recorded on the message, shown on the dashboard
        message.status = "failed"
        message.error = str(e)[:500]
        db.commit()
        return message
    message.status = "sent"
    message.sent_at = now
    message.provider_message_id = result.get("id")
    message.provider_thread_id = result.get("thread_id")
    message.rfc_message_id = result.get("rfc_message_id")
    if school is not None and school.status == "not_contacted":
        school.status = "emailed"
    if row.first_sent_at is None:
        row.first_sent_at = now
    days = (row.follow_up_days or DEFAULT_FOLLOW_UPS)
    follow = db.query(OutreachMessage).filter(
        OutreachMessage.school_id == message.school_id, OutreachMessage.step == message.step + 1,
        OutreachMessage.status.in_(("draft", "approved")),
    ).first()
    if follow is not None:
        wait = days[message.step - 1] if message.step - 1 < len(days) else 5
        follow.not_before = now + timedelta(days=int(wait))
    db.commit()
    return message


def check_replies(db: Session, provider) -> dict:
    """Look at every sent thread for a reply, a bounce or an opt-out, and
    stop the sequence for that school."""
    replied = bounced = opted = 0
    since = _now() - timedelta(days=45)
    threads = {}
    for m in db.query(OutreachMessage).filter(
        OutreachMessage.status == "sent", OutreachMessage.provider_thread_id.isnot(None),
        OutreachMessage.sent_at >= since,
    ).all():
        threads.setdefault(m.school_id, m.provider_thread_id)
    for school_id, thread_id in threads.items():
        school = db.get(OutreachSchool, school_id)
        if school is None or school.status in CLOSED:
            continue
        try:
            others = provider.thread_replies(thread_id)
        except Exception:  # noqa: BLE001 - try again next time
            continue
        if not others:
            continue
        bounce = any(re.search(r"mailer-daemon|postmaster|mail delivery", o["from"], re.I) for o in others)
        if bounce:
            school.status = "bounced"
            bounced += 1
            cancel(db, [school_id], "The address bounced.")
            continue
        text = " ".join(o["snippet"] for o in others)
        if STOP_WORDS.search(text) or re.match(r"^\s*no\b", text, re.I):
            school.status = "opted_out"
            opted += 1
            cancel(db, [school_id], "They asked not to be contacted.")
        else:
            school.status = "replied"
            replied += 1
            cancel(db, [school_id], "They replied.")
        note = f"Reply ({_now().astimezone(IST):%d %b}): {text[:300]}"
        school.notes = f"{school.notes}\n{note}" if school.notes else note
    db.commit()
    return {"replied": replied, "bounced": bounced, "opted_out": opted}


def run_cycle(session_factory, now: datetime | None = None, rng=random) -> dict:
    """One turn of the background sender: maybe send one email, and look for
    replies every half hour."""
    now = now or _now()
    db = session_factory()
    out = {"sent": None, "checked": False}
    try:
        row = get_settings(db)
        provider = provider_for(row)
        if provider is None:
            return out
        last = _aware(row.last_reply_check_at)
        if last is None or now - last >= timedelta(minutes=30):
            check_replies(db, provider)
            row.last_reply_check_at = now
            db.commit()
            out["checked"] = True
        if not row.sending_enabled or not in_send_window(now):
            return out
        if sent_today(db, now) >= effective_daily_limit(row, now):
            return out
        due = _STATE.get("next_send_at")
        if due is not None and now < due:
            return out
        message = send_one(db, row, provider, now)
        if message is not None:
            out["sent"] = message.id
            _STATE["next_send_at"] = now + timedelta(minutes=rng.uniform(*GAP_MINUTES))
        return out
    finally:
        db.close()


_SCHEDULER_STARTED = False


def start_scheduler(session_factory, every_seconds: int = 90) -> None:
    """Run the sender in the background for as long as the server is up."""
    global _SCHEDULER_STARTED
    if _SCHEDULER_STARTED:
        return
    _SCHEDULER_STARTED = True

    def loop():
        while True:
            try:
                run_cycle(session_factory)
            except Exception:  # noqa: BLE001 - never let the loop die
                log.exception("outreach cycle failed")
            time.sleep(every_seconds)

    threading.Thread(target=loop, daemon=True, name="outreach-sender").start()
