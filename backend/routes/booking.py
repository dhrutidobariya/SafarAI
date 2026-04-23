from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import User
from schemas import BookingHistoryOut, BookRequest
from services.auth_service import get_current_user
from services.booking_service import create_booking, get_booking_with_details, get_user_bookings, serialize_booking

router = APIRouter(tags=["booking"])


@router.post("/book", response_model=BookingHistoryOut)
def book(payload: BookRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    train_payload = payload.train.model_dump() if hasattr(payload.train, "model_dump") else payload.train.dict()
    booking = create_booking(
        db,
        user.id,
        train_payload,
        payload.seats,
        payload.seat_preference,
    )
    detailed_booking = get_booking_with_details(db, booking.id, user.id)
    return serialize_booking(detailed_booking)


@router.get("/history", response_model=list[BookingHistoryOut])
def history(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return get_user_bookings(db, user.id)
