from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.services.uploads import read_upload
from app.core.access import require_school_access
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.school import Room
from app.models.user import User
from app.schemas.bulk_import import BulkImportOut
from app.schemas.room import RoomCreate, RoomOut, RoomUpdate
from app.services.bulk_import import TEMPLATES, import_rooms, parse_rows

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


@router.post("", response_model=RoomOut, status_code=201)
def create_room(payload: RoomCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_school_access(db, current_user, payload.school_id, min_role="admin")
    room = Room(**payload.model_dump())
    db.add(room)
    db.commit()
    db.refresh(room)
    return room


@router.get("", response_model=list[RoomOut])
def list_rooms(school_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_school_access(db, current_user, school_id)
    return db.query(Room).filter(Room.school_id == school_id).all()


@router.get("/{room_id}", response_model=RoomOut)
def get_room(room_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    require_school_access(db, current_user, room.school_id)
    return room


@router.put("/{room_id}", response_model=RoomOut)
def update_room(room_id: int, payload: RoomUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    require_school_access(db, current_user, room.school_id, min_role="admin")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(room, field, value)
    db.commit()
    db.refresh(room)
    return room


@router.delete("/{room_id}", status_code=204)
def delete_room(room_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    require_school_access(db, current_user, room.school_id, min_role="admin")
    db.delete(room)
    db.commit()


@router.get("/bulk-import/template")
def download_rooms_template():
    return Response(
        content=TEMPLATES["rooms"],
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="rooms_template.csv"'},
    )


@router.post("/bulk-import", response_model=BulkImportOut)
async def bulk_import_rooms(
    school_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a CSV or .xlsx of rooms (columns: name, capacity, room_type)
    instead of adding them one at a time. See app/services/bulk_import.py."""
    require_school_access(db, current_user, school_id, min_role="admin")
    content = await read_upload(file)
    try:
        rows = parse_rows(file.filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    result = import_rooms(db, school_id, rows)
    return BulkImportOut(created=result.created, updated=result.updated, errors=result.errors)
