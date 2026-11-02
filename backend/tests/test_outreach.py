"""
Sales outreach from the admin page: importing the school list, finding the
principal on a school's website, drafting, approval, slow sending, follow-ups
in the same thread, and stopping on a reply, an opt-out or a bounce.

Nothing here touches Gmail or the internet: the mailbox is a fake that records
what it was asked to send, and websites are canned HTML.
"""
import io
from datetime import datetime, timedelta, timezone

import openpyxl
import pytest

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.outreach import OutreachMessage, OutreachSchool
from app.services import outreach as svc
from tests.conftest import signup, verify_email

ADMIN = "staff@timetablz.com"
IST = timezone(timedelta(hours=5, minutes=30))
# A Tuesday at 11:00 India time - inside the sending window.
TUESDAY_11 = datetime(2026, 11, 3, 11, 0, tzinfo=IST).astimezone(timezone.utc)


class FakeMailbox:
    def __init__(self):
        self.sent = []
        self.replies = {}
        self.fail_next = None

    def send(self, to, subject, body, from_name, thread_id=None, in_reply_to=None):
        if self.fail_next:
            error, self.fail_next = self.fail_next, None
            raise svc.MailboxError(error)
        n = len(self.sent) + 1
        self.sent.append({"to": to, "subject": subject, "body": body, "thread_id": thread_id,
                          "in_reply_to": in_reply_to})
        return {"id": f"m{n}", "thread_id": thread_id or f"t{n}", "rfc_message_id": f"<id{n}@x>"}

    def thread_replies(self, thread_id):
        return self.replies.get(thread_id, [])


@pytest.fixture
def staff(client, monkeypatch):
    monkeypatch.setattr(settings, "platform_admin_emails", ADMIN)
    _, h = signup(client, email=ADMIN)
    verify_email(ADMIN)
    return h


@pytest.fixture
def mailbox():
    box = FakeMailbox()
    svc.set_provider(box)
    svc._STATE["next_send_at"] = None
    yield box
    svc.set_provider(None)


def _workbook() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CBSE schools"
    ws.append(["School", "Group / chain", "Board", "Classes up to", "Type", "Priority", "Website",
               "Email (school website)", "Email source / note", "Area (fill in)", "Status"])
    ws.append(["Sunrise Vidyalaya", None, "CBSE", "Class 12", "Private", "High", "https://sunrise.example",
               "office@sunrise.example; principal@sunrise.example", "https://sunrise.example/contact", "Adyar",
               "Not contacted"])
    ws.append(["Lotus Public School", "Lotus group", "CBSE", "Class 10", "Private", "Medium", None, None, None, None, None])
    ws.append(["Lotus Public School - Annex", "Lotus group", "CBSE", "Class 10", "Private", "Medium", None,
               "info@lotus.example", None, None, None])
    sub = wb.create_sheet("Suburbs (CBSE)")
    sub.append(["School", "District", "Group / chain", "Board", "Classes up to", "Priority", "Website",
                "Email (school website)"])
    sub.append(["Hill View School", "Chengalpattu", None, "CBSE", "Class 12", "High", None, "hv@hill.example"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _import(client, staff):
    r = client.post("/api/admin/outreach/import", headers=staff,
                    files={"file": ("schools.xlsx", _workbook(), "application/octet-stream")})
    assert r.status_code == 200, r.text
    return r.json()


def _schools(client, staff, **params):
    return {s["name"]: s for s in client.get("/api/admin/outreach/schools", headers=staff, params=params).json()["schools"]}


def _cycle(now):
    return svc.run_cycle(SessionLocal, now=now)


# ---------------------------------------------------------------------------


def test_the_outreach_api_is_hidden_from_everyone_else(client):
    _, h = signup(client, email="head@school.in")
    assert client.get("/api/admin/outreach/overview", headers=h).status_code == 404


def test_importing_the_workbook_adds_schools_and_keeps_what_was_found_since(client, staff):
    assert _import(client, staff) == {"added": 4, "updated": 0, "total": 4}
    schools = _schools(client, staff)
    sunrise = schools["Sunrise Vidyalaya"]
    assert sunrise["district"] == "Chennai" and sunrise["area"] == "Adyar"
    assert sunrise["emails"] == ["office@sunrise.example", "principal@sunrise.example"]
    assert schools["Hill View School"]["district"] == "Chengalpattu"
    # A status set by hand and a principal found later survive a re-import.
    client.patch(f"/api/admin/outreach/schools/{sunrise['id']}", headers=staff,
                 json={"status": "demo_booked", "principal_name": "Dr. Meena Iyer"})
    assert _import(client, staff)["added"] == 0
    again = _schools(client, staff)["Sunrise Vidyalaya"]
    assert again["status"] == "demo_booked" and again["principal_name"] == "Dr. Meena Iyer"


def test_the_principal_is_read_from_the_schools_disclosure_page():
    pages = {
        "https://sunrise.example": '<a href="/about">About</a> <a href="/mandatory-disclosure">Mandatory Disclosure</a>',
        "https://sunrise.example/mandatory-disclosure": (
            "<table><tr><td>Name of the Principal</td><td>Dr. Meena Iyer</td></tr>"
            "<tr><td>Vice Principal</td><td>Mr. R. Kumar</td></tr>"
            "<tr><td>Email</td><td>principal@sunrise.example</td></tr></table>"
        ),
        "https://sunrise.example/about": "<p>Founded 1990.</p>",
    }
    found = svc.find_contacts_for("https://sunrise.example", fetch=pages.get)
    assert found["principal_name"] == "Dr. Meena Iyer"
    assert found["source"] == "https://sunrise.example/mandatory-disclosure"
    assert found["contact_name"] == "Mr. R. Kumar" and found["contact_role"] == "Vice Principal"
    assert "principal@sunrise.example" in found["emails"]


@pytest.mark.parametrize("text,name", [
    ("Principal: Mrs. Anitha Raghavan", "Mrs. Anitha Raghavan"),
    ("Dr. S. Lakshmi\nPrincipal", "Dr. S. Lakshmi"),
    ("Sr. Mary Joseph, Principal", "Sr. Mary Joseph"),
    ("PRINCIPAL - Ms. Kavitha Rao\nEmail: x@y.in", "Ms. Kavitha Rao"),
])
def test_principal_names_in_the_usual_layouts(text, name):
    assert svc.extract_people(text).get("principal_name") == name


def test_a_page_with_no_principal_named_finds_nothing():
    assert "principal_name" not in svc.extract_people("Welcome to our school. Message from the Principal desk.")


def test_find_contacts_updates_the_schools(client, staff, monkeypatch):
    _import(client, staff)
    sunrise = _schools(client, staff)["Sunrise Vidyalaya"]
    monkeypatch.setattr(svc, "_fetch", lambda url: "<p>Principal: Dr. Meena Iyer</p>")
    svc.start_find_contacts([sunrise["id"]], SessionLocal, background=False)
    assert _schools(client, staff)["Sunrise Vidyalaya"]["principal_name"] == "Dr. Meena Iyer"


def test_drafts_are_personal_and_need_approval(client, staff, mailbox):
    _import(client, staff)
    schools = _schools(client, staff)
    sunrise, lotus = schools["Sunrise Vidyalaya"], schools["Lotus Public School - Annex"]
    client.patch(f"/api/admin/outreach/schools/{sunrise['id']}", headers=staff, json={"principal_name": "Dr. Meena Iyer"})
    no_email = schools["Lotus Public School"]
    r = client.post("/api/admin/outreach/drafts", headers=staff,
                    json={"school_ids": [sunrise["id"], lotus["id"], no_email["id"]]})
    assert r.json() == {"created": 2, "skipped": 1}  # no address for the other Lotus school
    drafts = client.get("/api/admin/outreach/messages", headers=staff, params={"status": "draft"}).json()
    first = next(m for m in drafts if m["school_id"] == sunrise["id"] and m["step"] == 1)
    assert first["to_email"] == "office@sunrise.example"
    assert first["body"].startswith("Dear Dr. Iyer,")
    assert "Class 12" not in first["body"] and "up to 12" in first["body"] and "Adyar" in first["body"]
    assert "reply \"no\"" in first["body"]
    lotus_first = next(m for m in drafts if m["school_id"] == lotus["id"] and m["step"] == 1)
    assert lotus_first["body"].startswith("Dear Principal,") and "Lotus group" in lotus_first["body"]
    # Drafting twice doesn't make a second sequence.
    assert client.post("/api/admin/outreach/drafts", headers=staff, json={"school_ids": [sunrise["id"]]}).json()["created"] == 0
    # Nothing goes out until approved, even with sending on.
    client.put("/api/admin/outreach/settings", headers=staff, json={"sending_enabled": True})
    _cycle(TUESDAY_11)
    assert mailbox.sent == []


def test_approved_emails_go_slowly_inside_school_hours_then_follow_up_in_thread(client, staff, mailbox):
    _import(client, staff)
    schools = _schools(client, staff)
    ids = [schools["Sunrise Vidyalaya"]["id"], schools["Hill View School"]["id"]]
    client.post("/api/admin/outreach/drafts", headers=staff, json={"school_ids": ids})
    client.post("/api/admin/outreach/approve", headers=staff, json={"school_ids": ids})
    client.put("/api/admin/outreach/settings", headers=staff, json={"sending_enabled": True})

    sunday = datetime(2026, 11, 1, 11, 0, tzinfo=IST).astimezone(timezone.utc)
    _cycle(sunday)
    assert mailbox.sent == []  # not on a Sunday
    _cycle(TUESDAY_11)
    assert len(mailbox.sent) == 1
    _cycle(TUESDAY_11 + timedelta(minutes=2))
    assert len(mailbox.sent) == 1  # a few minutes apart, not all at once
    _cycle(TUESDAY_11 + timedelta(minutes=20))
    assert len(mailbox.sent) == 2
    assert {m["to"] for m in mailbox.sent} == {"office@sunrise.example", "hv@hill.example"}
    assert _schools(client, staff)["Sunrise Vidyalaya"]["status"] == "emailed"

    # The follow-up waits its four days, then goes in the same thread.
    _cycle(TUESDAY_11 + timedelta(days=1, minutes=30))
    assert len(mailbox.sent) == 2
    _cycle(TUESDAY_11 + timedelta(days=4, minutes=40))
    follow = mailbox.sent[2]
    assert follow["subject"].startswith("Re: ") and follow["thread_id"] in ("t1", "t2")
    assert follow["in_reply_to"] in ("<id1@x>", "<id2@x>")


def test_a_reply_stops_the_sequence_and_an_opt_out_is_remembered(client, staff, mailbox):
    _import(client, staff)
    schools = _schools(client, staff)
    ids = [schools["Sunrise Vidyalaya"]["id"], schools["Hill View School"]["id"]]
    client.post("/api/admin/outreach/drafts", headers=staff, json={"school_ids": ids})
    client.post("/api/admin/outreach/approve", headers=staff, json={"school_ids": ids})
    client.put("/api/admin/outreach/settings", headers=staff, json={"sending_enabled": True})
    _cycle(TUESDAY_11)
    _cycle(TUESDAY_11 + timedelta(minutes=20))
    threads = {m["to"]: f"t{i + 1}" for i, m in enumerate(mailbox.sent)}
    mailbox.replies[threads["office@sunrise.example"]] = [{"from": "Office <office@sunrise.example>",
                                                           "snippet": "Yes, please call us on Monday."}]
    mailbox.replies[threads["hv@hill.example"]] = [{"from": "hv@hill.example", "snippet": "Please remove me from your list"}]
    r = client.post("/api/admin/outreach/check-replies", headers=staff)
    assert r.json() == {"replied": 1, "bounced": 0, "opted_out": 1}
    after = _schools(client, staff)
    assert after["Sunrise Vidyalaya"]["status"] == "replied" and "call us on Monday" in after["Sunrise Vidyalaya"]["notes"]
    assert after["Hill View School"]["status"] == "opted_out"
    _cycle(TUESDAY_11 + timedelta(days=5))
    assert len(mailbox.sent) == 2  # no follow-ups to either
    # An opted-out school can't be drafted again.
    assert client.post("/api/admin/outreach/drafts", headers=staff,
                       json={"school_ids": [after["Hill View School"]["id"]]}).json()["created"] == 0


def test_a_bounce_marks_the_school(client, staff, mailbox):
    _import(client, staff)
    sid = _schools(client, staff)["Hill View School"]["id"]
    client.post("/api/admin/outreach/drafts", headers=staff, json={"school_ids": [sid]})
    client.post("/api/admin/outreach/approve", headers=staff, json={"school_ids": [sid]})
    client.put("/api/admin/outreach/settings", headers=staff, json={"sending_enabled": True})
    _cycle(TUESDAY_11)
    mailbox.replies["t1"] = [{"from": "Mail Delivery Subsystem <mailer-daemon@googlemail.com>",
                              "snippet": "Address not found"}]
    client.post("/api/admin/outreach/check-replies", headers=staff)
    assert _schools(client, staff)["Hill View School"]["status"] == "bounced"


def test_the_daily_limit_starts_low_and_never_passes_the_cap(client, staff, mailbox):
    db = SessionLocal()
    try:
        row = svc.get_settings(db)
        row.daily_limit = 40
        assert svc.effective_daily_limit(row) == 10  # nothing sent yet: warming up
        row.first_sent_at = datetime.now(timezone.utc) - timedelta(days=9)
        assert svc.effective_daily_limit(row) == 20
        row.first_sent_at = datetime.now(timezone.utc) - timedelta(days=30)
        assert svc.effective_daily_limit(row) == 40
        db.rollback()
    finally:
        db.close()
    assert client.put("/api/admin/outreach/settings", headers=staff, json={"daily_limit": 100}).status_code == 422


def test_sending_stops_at_the_days_limit(client, staff, mailbox):
    db = SessionLocal()
    try:
        for i in range(12):
            db.add(OutreachSchool(name=f"School {i}", emails=[f"s{i}@x.example"], status="not_contacted"))
        db.commit()
    finally:
        db.close()
    ids = [s["id"] for s in _schools(client, staff).values()]
    client.post("/api/admin/outreach/drafts", headers=staff, json={"school_ids": ids})
    client.post("/api/admin/outreach/approve", headers=staff, json={"school_ids": ids})
    client.put("/api/admin/outreach/settings", headers=staff, json={"sending_enabled": True, "daily_limit": 30})
    for minute in range(0, 300, 20):
        _cycle(TUESDAY_11 + timedelta(minutes=minute))
    assert len(mailbox.sent) == 10  # warm-up limit for a new mailbox


def test_a_refused_email_is_marked_failed_and_shown(client, staff, mailbox):
    _import(client, staff)
    sid = _schools(client, staff)["Hill View School"]["id"]
    client.post("/api/admin/outreach/drafts", headers=staff, json={"school_ids": [sid]})
    client.post("/api/admin/outreach/approve", headers=staff, json={"school_ids": [sid]})
    client.put("/api/admin/outreach/settings", headers=staff, json={"sending_enabled": True})
    mailbox.fail_next = "Gmail said 400: invalid recipient"
    _cycle(TUESDAY_11)
    failed = client.get("/api/admin/outreach/messages", headers=staff, params={"status": "failed"}).json()
    assert len(failed) == 1 and "invalid recipient" in failed[0]["error"]


def test_sending_needs_a_mailbox(client, staff):
    r = client.put("/api/admin/outreach/settings", headers=staff, json={"sending_enabled": True})
    assert r.status_code == 400 and "mailbox" in r.json()["detail"]


def test_overview_counts(client, staff, mailbox):
    _import(client, staff)
    o = client.get("/api/admin/outreach/overview", headers=staff).json()
    assert o["schools"] == 4 and o["with_email"] == 3
    assert o["by_status"]["not_contacted"] == 4 and o["sending_enabled"] is False


def test_closing_a_school_by_hand_stops_its_emails(client, staff, mailbox):
    _import(client, staff)
    sid = _schools(client, staff)["Hill View School"]["id"]
    client.post("/api/admin/outreach/drafts", headers=staff, json={"school_ids": [sid]})
    client.post("/api/admin/outreach/approve", headers=staff, json={"school_ids": [sid]})
    client.patch(f"/api/admin/outreach/schools/{sid}", headers=staff, json={"status": "not_interested"})
    db = SessionLocal()
    try:
        assert {m.status for m in db.query(OutreachMessage).filter(OutreachMessage.school_id == sid)} == {"cancelled"}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Zoho Mail


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body, self.text = status, body, str(body)

    def json(self):
        return self._body


class FakeZoho:
    """Stands in for Zoho's token and Mail API endpoints."""

    def __init__(self):
        self.calls = []
        self.search_results = {}
        self.reply_fails = False

    def post(self, url, data=None, timeout=None):
        self.calls.append(("POST", url, data))
        return _Resp(200, {"access_token": "at", "refresh_token": "rt", "expires_in": 3600})

    def get(self, url, headers=None, timeout=None):
        self.calls.append(("GET", url, None))
        return _Resp(200, {"data": [{"accountId": 555, "primaryEmailAddress": "arpith@timetablz.com"}]})

    def request(self, method, url, headers=None, timeout=None, json=None, params=None):
        self.calls.append((method, url, json or params))
        assert headers["Authorization"] == "Zoho-oauthtoken at"
        if method == "POST" and url.rstrip("/").split("/")[-1] != "messages":
            if self.reply_fails:
                return _Resp(404, {"status": {"code": 404}})
            return _Resp(200, {"data": {"messageId": "222"}})
        if method == "POST":
            return _Resp(200, {"data": {"messageId": "111"}})
        return _Resp(200, {"data": self.search_results.get(params["searchKey"].split("::")[0], [])})


@pytest.fixture
def zoho(monkeypatch):
    fake = FakeZoho()
    monkeypatch.setattr(svc.httpx, "post", fake.post)
    monkeypatch.setattr(svc.httpx, "get", fake.get)
    monkeypatch.setattr(svc.httpx, "request", fake.request)
    monkeypatch.setattr(settings, "outreach_zoho_client_id", "cid")
    monkeypatch.setattr(settings, "outreach_zoho_client_secret", "secret")
    return fake


def test_zoho_sends_the_first_email_then_follow_ups_as_replies_to_it(zoho):
    box = svc.ZohoProvider("rt", "arpith@timetablz.com", "555", "mail.zoho.in")
    first = box.send(to="office@sunrise.in", subject="Hello", body="Dear Sir", from_name="Arpith")
    method, url, body = zoho.calls[-1]
    assert url == "https://mail.zoho.in/api/accounts/555/messages"
    assert body["fromAddress"] == "arpith@timetablz.com" and body["mailFormat"] == "plaintext"
    assert zoho.calls[0][1] == "https://accounts.zoho.in/oauth/v2/token"
    assert first["id"] == "111" and first["thread_id"].startswith("office@sunrise.in|")

    follow = box.send(to="office@sunrise.in", subject="Re: Hello", body="Following up", from_name="Arpith",
                      thread_id=first["thread_id"], in_reply_to=first["rfc_message_id"])
    method, url, body = zoho.calls[-1]
    assert url.endswith("/messages/111") and body["action"] == "reply"
    assert follow["thread_id"] == first["thread_id"] and follow["rfc_message_id"] == "111"


def test_zoho_sends_a_follow_up_fresh_if_the_first_email_cant_be_replied_to(zoho):
    zoho.reply_fails = True
    box = svc.ZohoProvider("rt", "arpith@timetablz.com", "555", "mail.zoho.in")
    box.send(to="a@b.in", subject="Re: Hi", body="x", from_name="A", thread_id="a@b.in|02-Nov-2026",
             in_reply_to="111")
    assert zoho.calls[-1][1].endswith("/accounts/555/messages")


def test_zoho_finds_replies_and_bounces_by_searching_the_inbox(zoho, client, staff):
    zoho.search_results["sender:office@sunrise.in"] = [
        {"fromAddress": "office@sunrise.in", "summary": "Please call us next week"}]
    zoho.search_results["sender:mailer-daemon"] = []
    box = svc.ZohoProvider("rt", "arpith@timetablz.com", "555", "mail.zoho.in")
    found = box.thread_replies("office@sunrise.in|02-Nov-2026")
    assert found == [{"from": "office@sunrise.in", "snippet": "Please call us next week"}]
    keys = [c[2]["searchKey"] for c in zoho.calls if c[0] == "GET" and isinstance(c[2], dict)]
    assert "sender:office@sunrise.in::fromDate:02-Nov-2026" in keys
    assert any(k.startswith("sender:mailer-daemon::entire:office@sunrise.in") for k in keys)


def test_connecting_zoho_stores_the_mailbox_and_sends_through_it(client, staff, zoho):
    r = client.get("/api/admin/outreach/zoho/connect", headers=staff)
    assert r.status_code == 200, r.text
    url = r.json()["url"]
    assert url.startswith("https://accounts.zoho.in/oauth/v2/auth?") and "ZohoMail.messages.ALL" in url.replace("%2C", ",")
    from urllib.parse import parse_qs, urlparse
    state = parse_qs(urlparse(url).query)["state"][0]
    r = client.get("/api/admin/outreach/zoho/callback",
                   params={"code": "c", "state": state, "accounts-server": "https://accounts.zoho.in"},
                   follow_redirects=False)
    assert r.status_code in (302, 307) and "gmail_connected" in r.headers["location"]
    ov = client.get("/api/admin/outreach/overview", headers=staff).json()
    assert ov["mailbox"] == "arpith@timetablz.com" and ov["mailbox_provider"] == "zoho"
    db = SessionLocal()
    try:
        assert isinstance(svc.provider_for(svc.get_settings(db)), svc.ZohoProvider)
    finally:
        db.close()


def test_a_zoho_callback_from_a_strange_server_is_refused(client, staff, zoho):
    url = client.get("/api/admin/outreach/zoho/connect", headers=staff).json()["url"]
    from urllib.parse import parse_qs, urlparse
    state = parse_qs(urlparse(url).query)["state"][0]
    r = client.get("/api/admin/outreach/zoho/callback",
                   params={"code": "c", "state": state, "accounts-server": "https://evil.example.com"},
                   follow_redirects=False)
    assert "gmail_failed" in r.headers["location"]
    assert client.get("/api/admin/outreach/overview", headers=staff).json()["mailbox_connected"] is False
