"""
The admin page's Outreach section: Timetablz's own sales pipeline. Platform
admins only - see app/services/outreach.py for how it works.

    GET    /api/admin/outreach/overview          numbers, mailbox and sending state
    GET    /api/admin/outreach/schools           the list, filtered
    POST   /api/admin/outreach/schools           add one school
    PATCH  /api/admin/outreach/schools/{id}      edit status, contacts, notes
    DELETE /api/admin/outreach/schools/{id}
    POST   /api/admin/outreach/import            add schools from the workbook
    POST   /api/admin/outreach/find-contacts     read school websites for names
    GET    /api/admin/outreach/job               progress of that
    POST   /api/admin/outreach/drafts            write sequences for schools
    GET    /api/admin/outreach/messages          drafts, queue, sent
    PATCH  /api/admin/outreach/messages/{id}     edit a draft
    POST   /api/admin/outreach/approve           approve schools' sequences
    POST   /api/admin/outreach/cancel            stop schools' sequences
    GET    /api/admin/outreach/settings
    PUT    /api/admin/outreach/settings
    GET    /api/admin/outreach/gmail/connect     where to send the browser
    GET    /api/admin/outreach/gmail/callback    Google sends it back here
    POST   /api/admin/outreach/gmail/disconnect
    POST   /api/admin/outreach/send-test         one email to the mailbox itself
    POST   /api/admin/outreach/check-replies     look for replies now
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings as app_settings
from app.core.database import SessionLocal, get_db
from app.models.outreach import STATUSES, OutreachMessage, OutreachSchool
from app.models.user import User
from app.routers.admin import require_platform_admin
from app.services import outreach as svc

router = APIRouter(prefix="/api/admin/outreach", tags=["outreach"])


def _school_out(s: OutreachSchool) -> dict:
    return {
        "id": s.id, "name": s.name, "district": s.district, "area": s.area, "board": s.board,
        "classes_up_to": s.classes_up_to, "school_type": s.school_type, "priority": s.priority,
        "group_name": s.group_name, "website": s.website, "emails": s.emails or [],
        "to_email": s.to_email, "recipient": s.recipient, "email_source": s.email_source, "phone": s.phone,
        "principal_name": s.principal_name, "contact_name": s.contact_name, "contact_role": s.contact_role,
        "contact_source": s.contact_source,
        "contacts_checked_at": s.contacts_checked_at.isoformat() if s.contacts_checked_at else None,
        "status": s.status, "notes": s.notes, "next_step": s.next_step, "next_date": s.next_date,
    }


def _message_out(m: OutreachMessage, school: OutreachSchool | None = None) -> dict:
    return {
        "id": m.id, "school_id": m.school_id, "school_name": school.name if school else None,
        "step": m.step, "to_email": m.to_email, "subject": m.subject, "body": m.body, "status": m.status,
        "approved_at": m.approved_at.isoformat() if m.approved_at else None,
        "not_before": m.not_before.isoformat() if m.not_before else None,
        "sent_at": m.sent_at.isoformat() if m.sent_at else None, "error": m.error,
    }


# ---------------------------------------------------------------------------


@router.get("/overview")
def overview(db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    row = svc.get_settings(db)
    by_status = dict(db.query(OutreachSchool.status, func.count(OutreachSchool.id)).group_by(OutreachSchool.status).all())
    by_message = dict(db.query(OutreachMessage.status, func.count(OutreachMessage.id)).group_by(OutreachMessage.status).all())
    total = db.query(OutreachSchool).count()
    with_email = sum(1 for s in db.query(OutreachSchool).all() if s.recipient)
    with_principal = db.query(OutreachSchool).filter(OutreachSchool.principal_name.isnot(None)).count()
    awaiting = db.query(func.count(func.distinct(OutreachMessage.school_id))).filter(
        OutreachMessage.status == "draft").scalar() or 0
    queued = db.query(func.count(func.distinct(OutreachMessage.school_id))).filter(
        OutreachMessage.status == "approved", OutreachMessage.step == 1).scalar() or 0
    week = datetime.now(timezone.utc) - timedelta(days=7)
    return {
        "schools": total,
        "with_email": with_email,
        "with_principal": with_principal,
        "by_status": {s: by_status.get(s, 0) for s in STATUSES},
        "messages": by_message,
        "awaiting_approval": awaiting,
        "queued": queued,
        "sent_this_week": db.query(OutreachMessage).filter(
            OutreachMessage.status == "sent", OutreachMessage.sent_at >= week).count(),
        "sent_today": svc.sent_today(db),
        "daily_limit": svc.effective_daily_limit(row),
        "daily_limit_set": row.daily_limit,
        "sending_enabled": row.sending_enabled,
        "in_send_window": svc.in_send_window(),
        "mailbox": row.gmail_address,
        "mailbox_connected": bool(row.gmail_refresh_token),
        "gmail_configured": svc.gmail_configured(),
        "job": svc.JOB,
    }


@router.get("/schools")
def list_schools(
    q: str | None = None, status: str | None = None, priority: str | None = None,
    district: str | None = None, has_email: bool | None = None, has_principal: bool | None = None,
    db: Session = Depends(get_db), admin: User = Depends(require_platform_admin),
):
    query = db.query(OutreachSchool)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(OutreachSchool.name.ilike(like), OutreachSchool.area.ilike(like),
                                 OutreachSchool.group_name.ilike(like)))
    if status:
        query = query.filter(OutreachSchool.status == status)
    if priority:
        query = query.filter(OutreachSchool.priority.ilike(f"{priority}%"))
    if district:
        query = query.filter(OutreachSchool.district == district)
    if has_principal is not None:
        query = query.filter(OutreachSchool.principal_name.isnot(None) if has_principal
                             else OutreachSchool.principal_name.is_(None))
    schools = query.order_by(OutreachSchool.name).all()
    if has_email is not None:
        schools = [s for s in schools if bool(s.recipient) == has_email]
    stage = {}
    for m in db.query(OutreachMessage).filter(OutreachMessage.school_id.in_([s.id for s in schools])).all():
        current = stage.get(m.school_id)
        rank = {"draft": 1, "approved": 2, "sent": 3, "failed": 0, "cancelled": -1}.get(m.status, 0)
        if m.status == "sent":
            rank = 3 + m.step
        if current is None or rank > current[0]:
            stage[m.school_id] = (rank, m.status, m.step)
    out = []
    for s in schools:
        item = _school_out(s)
        st = stage.get(s.id)
        item["sequence"] = None if st is None else {"status": st[1], "step": st[2]}
        out.append(item)
    districts = sorted({d for (d,) in db.query(OutreachSchool.district).distinct() if d})
    return {"schools": out, "districts": districts}


class SchoolIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    district: str | None = None
    area: str | None = None
    board: str | None = None
    classes_up_to: str | None = None
    priority: str | None = None
    group_name: str | None = None
    website: str | None = None
    emails: list[str] | None = None
    phone: str | None = None
    principal_name: str | None = None


@router.post("/schools", status_code=201)
def add_school(payload: SchoolIn, db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    data = payload.model_dump()
    data["emails"] = svc._split_emails(" ".join(data.get("emails") or [])) or None
    school = OutreachSchool(**data, status="not_contacted")
    db.add(school)
    db.commit()
    db.refresh(school)
    return _school_out(school)


class SchoolPatch(BaseModel):
    status: str | None = None
    notes: str | None = None
    next_step: str | None = None
    next_date: str | None = None
    to_email: str | None = None
    emails: list[str] | None = None
    phone: str | None = None
    principal_name: str | None = None
    contact_name: str | None = None
    contact_role: str | None = None
    area: str | None = None
    website: str | None = None
    priority: str | None = None


@router.patch("/schools/{school_id}")
def edit_school(school_id: int, payload: SchoolPatch, db: Session = Depends(get_db),
                admin: User = Depends(require_platform_admin)):
    school = db.get(OutreachSchool, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in STATUSES:
        raise HTTPException(status_code=400, detail="Unknown status.")
    if "emails" in data:
        data["emails"] = svc._split_emails(" ".join(data["emails"] or [])) or None
    if data.get("to_email"):
        found = svc._split_emails(data["to_email"])
        if not found:
            raise HTTPException(status_code=400, detail="That isn't an email address.")
        data["to_email"] = found[0]
    for k, v in data.items():
        setattr(school, k, v.strip() if isinstance(v, str) else v)
    # Closing a school by hand stops anything still waiting to go to it.
    if data.get("status") in svc.CLOSED:
        svc.cancel(db, [school.id], "Status changed by hand.")
    # A new address is where unsent emails now go.
    if "to_email" in data or "emails" in data:
        for m in db.query(OutreachMessage).filter(OutreachMessage.school_id == school.id,
                                                  OutreachMessage.status.in_(("draft", "approved"))).all():
            if school.recipient:
                m.to_email = school.recipient
    db.commit()
    db.refresh(school)
    return _school_out(school)


@router.delete("/schools/{school_id}", status_code=204)
def delete_school(school_id: int, db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    school = db.get(OutreachSchool, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    db.query(OutreachMessage).filter(OutreachMessage.school_id == school_id).delete()
    db.delete(school)
    db.commit()


@router.post("/import")
async def import_schools(file: UploadFile = File(...), db: Session = Depends(get_db),
                         admin: User = Depends(require_platform_admin)):
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="That file is too big.")
    try:
        return svc.import_workbook(db, data)
    except Exception as e:  # noqa: BLE001 - a broken file is a user error
        raise HTTPException(status_code=400, detail=f"Couldn't read that workbook: {e}") from e


class SchoolIds(BaseModel):
    school_ids: list[int] = Field(min_length=1, max_length=1000)


@router.post("/find-contacts")
def find_contacts(payload: SchoolIds, admin: User = Depends(require_platform_admin)):
    if svc.JOB.get("running"):
        raise HTTPException(status_code=409, detail="Already looking for contacts - wait for it to finish.")
    return svc.start_find_contacts(payload.school_ids, SessionLocal)


@router.get("/job")
def job(admin: User = Depends(require_platform_admin)):
    return svc.JOB


@router.post("/drafts")
def drafts(payload: SchoolIds, db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    return svc.create_drafts(db, payload.school_ids)


@router.get("/messages")
def messages(status: str | None = None, school_id: int | None = None, limit: int = 300,
             db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    query = db.query(OutreachMessage)
    if status:
        query = query.filter(OutreachMessage.status.in_(status.split(",")))
    if school_id:
        query = query.filter(OutreachMessage.school_id == school_id)
    order = OutreachMessage.sent_at.desc() if status == "sent" else OutreachMessage.id
    rows = query.order_by(order, OutreachMessage.step).limit(max(1, min(limit, 1000))).all()
    schools = {s.id: s for s in db.query(OutreachSchool).filter(
        OutreachSchool.id.in_({m.school_id for m in rows})).all()}
    return [_message_out(m, schools.get(m.school_id)) for m in rows]


class MessagePatch(BaseModel):
    subject: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=5000)


@router.patch("/messages/{message_id}")
def edit_message(message_id: int, payload: MessagePatch, db: Session = Depends(get_db),
                 admin: User = Depends(require_platform_admin)):
    m = db.get(OutreachMessage, message_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Email not found")
    if m.status not in ("draft", "approved"):
        raise HTTPException(status_code=400, detail="Only emails that haven't gone out can be edited.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    db.commit()
    return _message_out(m, db.get(OutreachSchool, m.school_id))


@router.post("/approve")
def approve(payload: SchoolIds, db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    return {"approved": svc.approve(db, payload.school_ids)}


@router.post("/cancel")
def cancel(payload: SchoolIds, db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    return {"cancelled": svc.cancel(db, payload.school_ids, "Stopped by hand.")}


def _settings_out(row) -> dict:
    return {
        "sender_name": row.sender_name, "signature": row.signature, "templates": svc.templates_of(row),
        "daily_limit": row.daily_limit, "follow_up_days": row.follow_up_days or svc.DEFAULT_FOLLOW_UPS,
        "sending_enabled": row.sending_enabled, "mailbox": row.gmail_address,
        "mailbox_connected": bool(row.gmail_refresh_token), "gmail_configured": svc.gmail_configured(),
        "hard_daily_cap": svc.HARD_DAILY_CAP, "effective_daily_limit": svc.effective_daily_limit(row),
    }


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    return _settings_out(svc.get_settings(db))


class Template(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)


class SettingsIn(BaseModel):
    sender_name: str | None = Field(default=None, max_length=80)
    signature: str | None = Field(default=None, max_length=600)
    templates: dict[str, Template] | None = None
    daily_limit: int | None = Field(default=None, ge=0, le=svc.HARD_DAILY_CAP)
    follow_up_days: list[int] | None = None
    sending_enabled: bool | None = None


@router.put("/settings")
def put_settings(payload: SettingsIn, db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    row = svc.get_settings(db)
    data = payload.model_dump(exclude_unset=True)
    if data.get("sending_enabled") and not row.gmail_refresh_token and svc._PROVIDER_OVERRIDE is None:
        raise HTTPException(status_code=400, detail="Connect a mailbox before turning sending on.")
    if "templates" in data and data["templates"] is not None:
        if set(data["templates"]) - {"1", "2", "3"}:
            raise HTTPException(status_code=400, detail="Templates are for emails 1, 2 and 3.")
        merged = svc.templates_of(row)
        merged.update({k: v for k, v in data["templates"].items()})
        data["templates"] = merged
    if "follow_up_days" in data and data["follow_up_days"] is not None:
        days = data["follow_up_days"]
        if len(days) != 2 or any(not (1 <= d <= 30) for d in days):
            raise HTTPException(status_code=400, detail="Give two follow-up gaps, each 1 to 30 days.")
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    return _settings_out(row)


def _state_token(user: User) -> str:
    return jwt.encode({"sub": str(user.id), "purpose": "outreach_gmail",
                       "exp": datetime.now(timezone.utc) + timedelta(minutes=15)},
                      app_settings.jwt_secret, algorithm="HS256")


@router.get("/gmail/connect")
def gmail_connect(admin: User = Depends(require_platform_admin)):
    if not svc.gmail_configured():
        raise HTTPException(status_code=400, detail=(
            "Gmail isn't set up on the server yet: add OUTREACH_GOOGLE_CLIENT_ID and "
            "OUTREACH_GOOGLE_CLIENT_SECRET in Railway."))
    params = {
        "client_id": app_settings.outreach_google_client_id,
        "redirect_uri": app_settings.outreach_google_redirect_uri,
        "response_type": "code",
        "scope": svc.GMAIL_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": _state_token(admin),
    }
    return {"url": "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)}


@router.get("/gmail/callback")
def gmail_callback(code: str | None = None, state: str | None = None, error: str | None = None,
                   db: Session = Depends(get_db)):
    # Google sends the browser here without our login token; the signed
    # state is what proves an admin started this.
    if error or not code or not state:
        return RedirectResponse("/admin?outreach=gmail_cancelled")
    try:
        claims = jwt.decode(state, app_settings.jwt_secret, algorithms=["HS256"])
        user = db.get(User, int(claims["sub"]))
        if claims.get("purpose") != "outreach_gmail" or user is None or not user.is_platform_admin:
            raise ValueError
    except Exception:  # noqa: BLE001
        return RedirectResponse("/admin?outreach=gmail_failed")
    try:
        result = svc.exchange_code(code)
    except svc.MailboxError:
        return RedirectResponse("/admin?outreach=gmail_failed")
    row = svc.get_settings(db)
    row.gmail_refresh_token = result["refresh_token"]
    row.gmail_address = result["address"]
    db.commit()
    return RedirectResponse("/admin?outreach=gmail_connected")


@router.post("/gmail/disconnect")
def gmail_disconnect(db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    row = svc.get_settings(db)
    row.gmail_refresh_token = None
    row.gmail_address = None
    row.sending_enabled = False
    db.commit()
    return _settings_out(row)


@router.post("/send-test")
def send_test(db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    row = svc.get_settings(db)
    provider = svc.provider_for(row)
    if provider is None:
        raise HTTPException(status_code=400, detail="Connect a mailbox first.")
    sample = db.query(OutreachSchool).filter(OutreachSchool.status == "not_contacted").first() or OutreachSchool(
        name="Sample School", classes_up_to="Class 12", area="Anna Nagar")
    subject, body = svc.render(svc.templates_of(row)["1"], sample, row, {})
    try:
        provider.send(to=row.gmail_address or admin.email, subject=f"[Test] {subject}", body=body,
                      from_name=row.sender_name or svc.DEFAULT_SENDER)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Sending failed: {e}") from e
    return {"sent_to": row.gmail_address or admin.email}


@router.post("/check-replies")
def check_replies(db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    row = svc.get_settings(db)
    provider = svc.provider_for(row)
    if provider is None:
        raise HTTPException(status_code=400, detail="Connect a mailbox first.")
    result = svc.check_replies(db, provider)
    row.last_reply_check_at = datetime.now(timezone.utc)
    db.commit()
    return result
