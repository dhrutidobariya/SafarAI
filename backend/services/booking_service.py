from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import Booking, Train


def search_trains(db: Session, source: str, destination: str, travel_date: date):
    return (
        db.query(Train)
        .filter(
            Train.source.ilike(source.strip()),
            Train.destination.ilike(destination.strip()),
            Train.travel_date == travel_date,
        )
        .all()
    )


def check_availability(db: Session, train_id: int, seats: int) -> dict:
    train = db.query(Train).filter(Train.id == train_id).first()
    if not train:
        raise HTTPException(status_code=404, detail="Train not found")
    if train.seats_available < seats:
        return {"available": False, "message": "सीट उपलब्ध नहीं (No seats available)"}
    return {"available": True, "message": "Seats available", "seats_left": train.seats_available}


import random

def create_booking(db: Session, user_id: int, train_id: int, seats: int, preference: str = "No Preference") -> Booking:
    train = db.query(Train).filter(Train.id == train_id).first()
    if not train:
        raise HTTPException(status_code=404, detail="Train not found")
    travel_date = train.travel_date
    if train.seats_available < seats:
        raise HTTPException(status_code=400, detail="सीट उपलब्ध नहीं (No seats available)")

    # Generate random seat numbers (e.g., S1-24, S1-25)
    seat_list = []
    for _ in range(seats):
        coach = random.choice(["S1", "S2", "S3", "B1", "B2", "A1"])
        num = random.randint(1, 72)
        pref_suffix = (f"({preference.upper()[0]})" if preference and preference != "No Preference" else "")
        seat_list.append(f"{coach}-{num}{pref_suffix}")
    
    seat_numbers_str = ", ".join(seat_list)

    total_fare = seats * train.fare_per_seat
    booking = Booking(
        user_id=user_id,
        train_id=train_id,
        seats=seats,
        seat_numbers=seat_numbers_str,
        seat_preference=preference,
        booking_date=travel_date,
        total_fare=total_fare,
        status="PENDING",
    )
    train.seats_available -= seats
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


def get_user_bookings(db: Session, user_id: int):
    return (
        db.query(Booking)
        .filter(Booking.user_id == user_id)
        .order_by(Booking.created_at.desc())
        .all()
    )
