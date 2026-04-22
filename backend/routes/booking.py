from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import User
from schemas import BookingHistoryOut, BookingOut, BookRequest
from services.auth_service import get_current_user
from services.booking_service import create_booking, get_user_bookings

router = APIRouter(tags=["booking"])


@router.post("/book", response_model=BookingOut)
def book(payload: BookRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return create_booking(db, user.id, payload.train_id, payload.seats)


@router.get("/history", response_model=list[BookingHistoryOut])
def history(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return get_user_bookings(db, user.id)
