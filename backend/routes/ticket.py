from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database import get_db
from models import User
from services.auth_service import get_current_user
from services.ticket_service import generate_ticket_pdf

router = APIRouter(tags=["ticket"])


@router.get("/ticket/{booking_id}")
def ticket(booking_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    path = generate_ticket_pdf(db, booking_id)
    return FileResponse(path=path, media_type="application/pdf", filename=f"ticket_{booking_id}.pdf")
