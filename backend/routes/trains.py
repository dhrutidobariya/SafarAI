from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from schemas import TrainOut
from services.booking_service import search_trains

router = APIRouter(tags=["trains"])


@router.get("/trains", response_model=list[TrainOut])
def get_trains(
    source: str = Query(...),
    destination: str = Query(...),
    travel_date: date = Query(...),
    seats: int = Query(1, ge=1, le=10),
    train_name: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return search_trains(db, source, destination, travel_date, seats=seats, train_name=train_name)
