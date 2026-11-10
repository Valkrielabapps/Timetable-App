"""
Emailing teachers a day's cover, with calendar invites.

Each teacher covering a lesson gets one email listing their extra periods,
with a calendar invite for each (one .ics with every event) - Gmail, Outlook
and Apple Mail put them in the teacher's calendar. Optionally everyone with
an email gets the day's whole arrangement too.

Emailing again after the cover changes updates the same calendar entries
(each lesson's cover has a fixed id), and a teacher no longer covering a
lesson gets a cancellation for it, so their calendar never shows cover they
aren't doing.

Periods don't store clock times; a label like "9:00-9:45" gives the event its
time (in the school's time zone, India unless the school profile says
otherwise), and otherwise the event is all day on that date.
"""
from __future__ import annotations

import html
import re
from collections import defaultdict
from datetime import date as date_type, datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.school import ClassGroup, Period, School, Subject, SubstitutionLog, Teacher
from app.services import email_service
from app.services.school_categories import category_of
from app.services.substitution_summary import _section_label, build_summary, log_date
from app.services.timetable_structure import lesson_numbers

_TIME = re.compile(r"(\d{1,2})[:.](\d{2})\s*(am|pm)?\s*(?:-|–|—|to)\s*(\d{1,2})[:.](\d{2})\s*(am|pm)?", re.I)


def _times(label: str | None) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """"9:00-9:45" / "1.30 pm to 2.15 pm" -> ((9, 0), (9, 45))."""
    m = _TIME.search(label or "")
    if not m:
        return None

    def hm(h, mi, ap, other_ap):
        h, mi = int(h), int(mi)
        ap = (ap or other_ap or "").lower()
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        if not ap and 1 <= h <= 6:
            h += 12  # "2:15" in a school day is afternoon
        return h, mi

    start = hm(m.group(1), m.group(2), m.group(3), m.group(6))
    end = hm(m.group(4), m.group(5), m.group(6), m.group(3))
    if not (0 <= start[0] < 24 and 0 <= end[0] < 24) or end <= start:
        return None
    return start, end


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics(events: list[dict], method: str, organizer: str, tz: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    seq = int(datetime.now(timezone.utc).timestamp())  # later sends always win
    lines = ["BEGIN:VCALENDAR", "PRODID:-//Timetablz//Cover//EN", "VERSION:2.0", "CALSCALE:GREGORIAN",
             f"METHOD:{method}"]
    for e in events:
        lines += ["BEGIN:VEVENT", f"UID:{e['uid']}", f"DTSTAMP:{stamp}", f"SEQUENCE:{seq}"]
        day = e["date"].strftime("%Y%m%d")
        if e.get("start"):
            (sh, sm), (eh, em) = e["start"], e["end"]
            lines += [f"DTSTART;TZID={tz}:{day}T{sh:02d}{sm:02d}00", f"DTEND;TZID={tz}:{day}T{eh:02d}{em:02d}00"]
        else:
            nxt = date_type.fromordinal(e["date"].toordinal() + 1).strftime("%Y%m%d")
            lines += [f"DTSTART;VALUE=DATE:{day}", f"DTEND;VALUE=DATE:{nxt}"]
        lines += [f"SUMMARY:{_esc(e['summary'])}", f"DESCRIPTION:{_esc(e['description'])}",
                  f"ORGANIZER;CN=Timetablz:mailto:{organizer}",
                  f"ATTENDEE;CN={_esc(e['teacher'])};RSVP=FALSE:mailto:{e['email']}",
                  f"STATUS:{'CANCELLED' if method == 'CANCEL' else 'CONFIRMED'}", "TRANSP:OPAQUE", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


_last_send = [0.0]


def _pace() -> None:
    """At most about two emails a second: Resend's default rate limit."""
    import time

    wait = 0.55 - (time.monotonic() - _last_send[0])
    if wait > 0:
        time.sleep(wait)
    _last_send[0] = time.monotonic()


def _organizer() -> str:
    m = re.search(r"<([^>]+)>", settings.email_from_address or "")
    return m.group(1) if m else (settings.email_from_address or "noreply@timetablz.com")


def notify(db: Session, school_id: int, day: date_type, category: str | None = None,
           everyone: bool = False) -> dict:
    """Email the day's cover. Returns what was sent and to whom it couldn't be."""
    school = db.get(School, school_id)
    overrides = (school.grade_categories or {}) if school else {}
    tz = ((school.profile or {}).get("timezone") if school else None) or "Asia/Kolkata"
    logs = [log for log in db.query(SubstitutionLog).filter(SubstitutionLog.school_id == school_id)
            .order_by(SubstitutionLog.id).all()
            if log_date(log) == day and (category is None or log.category in (None, category))]
    if not logs:
        raise ValueError("Save the cover for this date first.")
    periods = {p.id: p for p in db.query(Period).filter(Period.school_id == school_id)}
    numbers = lesson_numbers(periods.values())
    teachers = {t.id: t for t in db.query(Teacher).filter(Teacher.school_id == school_id)}
    sections = {c.id: c for c in db.query(ClassGroup).filter(ClassGroup.school_id == school_id)}
    subjects = {s.id: s.name for s in db.query(Subject).filter(Subject.school_id == school_id)}

    merged: dict[tuple, dict] = {}
    for log in logs:
        for change in log.changes or []:
            merged[(change["period_id"], change["class_group_id"], change["absent_teacher_id"])] = change

    events_by_teacher: dict[int, list[dict]] = defaultdict(list)
    for (pid, cgid, absent), change in merged.items():
        cg = sections.get(cgid)
        cat = change.get("category") or category_of(cg.grade if cg else None, overrides)
        if category is not None and cat != category:
            continue
        sub = change.get("substituting_teacher_id")
        if sub is None or sub not in teachers:
            continue
        p = periods.get(pid)
        when = f"Period {numbers[pid]}" if pid in numbers else (p.label if p and p.label else "A period")
        times = _times(p.label if p else None)
        subject = subjects.get(change.get("subject_id")) or "lesson"
        away = teachers.get(absent)
        events_by_teacher[sub].append({
            "uid": f"cover-{school_id}-{day.isoformat()}-{pid}-{cgid}@timetablz.com",
            "date": day, "start": times[0] if times else None, "end": times[1] if times else None,
            "order": p.order if p else 0,
            "summary": f"Cover: {_section_label(cg)} {subject} ({when})",
            "description": f"Covering for {away.name if away else 'a colleague'}. {when}, {_section_label(cg)}, {subject}.",
            "line": f"{when}: {_section_label(cg)} {subject}, for {away.name if away else 'a colleague'}",
            "teacher": teachers[sub].name, "email": (teachers[sub].email or "").strip(),
        })

    configured = bool(settings.resend_api_key)
    organizer = _organizer()
    school_name = school.name if school else "your school"
    nice_day = day.strftime("%A %d %B %Y").replace(" 0", " ")
    sent, no_email, failed = [], [], []
    reasons: set[str] = set()
    now_notified: dict[str, int] = {}
    for tid, events in events_by_teacher.items():
        events.sort(key=lambda e: e["order"])
        t = teachers[tid]
        for e in events:
            now_notified[e["uid"]] = tid
        if not t.email:
            no_email.append(t.name)
            continue
        items = "".join(f"<li>{html.escape(e['line'])}</li>" for e in events)
        body = (f"<p>Dear {html.escape(t.name)},</p><p>On <b>{nice_day}</b> you are covering:</p><ul>{items}</ul>"
                f"<p>The calendar invite attached puts {'this' if len(events) == 1 else 'these'} in your calendar.</p>"
                f"<p style='color:#64748b;font-size:12px'>Sent for {html.escape(school_name)} by Timetablz.</p>")
        _pace()
        ok = email_service.send_cover_email(
            t.email, f"Cover on {nice_day}: {len(events)} {'period' if len(events) == 1 else 'periods'}",
            body, _ics(events, "REQUEST", organizer, tz))
        if ok:
            sent.append(t.name)
        else:
            failed.append(t.name)
            reasons.add(email_service.last_error() or "unknown")

    # Cover that moved away from someone since they were last emailed.
    before: dict[str, int] = {}
    for log in logs:
        before.update(log.notified or {})
    cancelled = 0
    by_old: dict[int, list[str]] = defaultdict(list)
    for uid, tid in before.items():
        if now_notified.get(uid) != tid and tid in teachers and teachers[tid].email:
            by_old[tid].append(uid)
    for tid, uids in by_old.items():
        t = teachers[tid]
        events = [{"uid": u, "date": day, "summary": "Cover cancelled", "description": "No longer needed.",
                   "teacher": t.name, "email": t.email} for u in uids]
        body = (f"<p>Dear {html.escape(t.name)},</p><p>{'A cover' if len(uids) == 1 else f'{len(uids)} covers'} "
                f"you were given for <b>{nice_day}</b> {'is' if len(uids) == 1 else 'are'} no longer needed, and "
                "the calendar entry is removed.</p>")
        _pace()
        if email_service.send_cover_email(t.email, f"Cover on {nice_day} cancelled", body,
                                          _ics(events, "CANCEL", organizer, tz)):
            cancelled += len(uids)

    summary_sent, summary_failed = 0, []
    if everyone:
        s = build_summary(db, school_id, day, category)
        rows = "".join(
            f"<tr><td>{html.escape(r['period'])}</td><td>{html.escape(r['class_group'])}</td>"
            f"<td>{html.escape(r['subject'] or '')}</td><td>{html.escape(r['absent_teacher'])}</td>"
            f"<td>{html.escape(r['substitute'] or 'Not covered')}</td></tr>" for r in s["rows"])
        leave = ", ".join(x["teacher"] + ("" if x["periods"] is None else f" ({', '.join(x['periods'])})")
                          for x in s["on_leave"]) or "nobody recorded"
        body = (f"<p><b>Cover for {nice_day}</b></p><p>On leave: {html.escape(leave)}</p>"
                "<table border='1' cellpadding='4' style='border-collapse:collapse'>"
                "<tr><th>Period</th><th>Class</th><th>Subject</th><th>For</th><th>Covered by</th></tr>"
                f"{rows}</table><p style='color:#64748b;font-size:12px'>Sent for {html.escape(school_name)} by Timetablz.</p>")
        covering = set(events_by_teacher)
        for t in teachers.values():
            if t.email and t.id not in covering:
                _pace()
                if email_service.send_cover_email(t.email, f"Cover arrangement for {nice_day}", body, None):
                    summary_sent += 1
                else:
                    summary_failed.append(t.name)
                    reasons.add(email_service.last_error() or "unknown")

    newest = logs[-1]
    newest.notified = now_notified
    for log in logs[:-1]:
        log.notified = None
    db.commit()
    return {
        "email_configured": configured,
        "sent": sorted(sent),
        "no_email": sorted(no_email),
        "failed": sorted(failed),
        "cancelled": cancelled,
        "summary_sent": summary_sent,
        "summary_failed": sorted(summary_failed),
        # Why sending failed, if it did: the same reason usually applies to all.
        "errors": sorted(reasons),
    }
