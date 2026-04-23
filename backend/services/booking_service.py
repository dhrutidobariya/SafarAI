import random
from datetime import date, datetime
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from models import Booking, Payment
from services.train_service import TrainSearchError, search_trains as search_trains_from_api


def search_trains(db: Session, source: str, destination: str, travel_date: date, seats: int = 1, train_name: str | None = None):
    del db
    try:
        return search_trains_from_api(source, destination, travel_date.isoformat(), seats=seats, train_name=train_name)
    except TrainSearchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def build_pnr(booking_id: int) -> str:
    return f"PNR{booking_id:08d}"


def build_receipt_number(booking_id: int, payment_id: int | None = None) -> str:
    suffix = payment_id or 0
    return f"RCT-{booking_id:06d}-{suffix:04d}"


def serialize_payment(payment: Payment | None) -> dict | None:
    if not payment:
        return None

    return {
        "id": payment.id,
        "amount": payment.amount,
        "method": payment.method,
        "transaction_id": payment.transaction_id,
        "status": payment.status,
        "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
    }


def serialize_train_snapshot(booking: Booking) -> dict:
    fare_per_seat = round(float(booking.total_fare or 0) / max(int(booking.seats or 1), 1), 2)
    return {
        "id": str(booking.train_number or booking.train_id or booking.id),
        "train_id": booking.train_id,
        "train_number": booking.train_number,
        "train_name": booking.train_name,
        "source": booking.source,
        "destination": booking.destination,
        "travel_date": booking.booking_date.isoformat(),
        "departure_time": booking.departure_time or "N/A",
        "arrival_time": booking.arrival_time or "N/A",
        "seats_available": 0,
        "fare_per_seat": fare_per_seat,
        "total_fare": round(float(booking.total_fare or 0), 2),
        "data_source": booking.data_source or "api",
    }


def serialize_booking(booking: Booking) -> dict:
    payment = booking.payment
    return {
        "id": booking.id,
        "pnr": build_pnr(booking.id),
        "user_id": booking.user_id,
        "train_id": booking.train_id,
        "train_number": booking.train_number,
        "train_name": booking.train_name,
        "source": booking.source,
        "destination": booking.destination,
        "departure_time": booking.departure_time,
        "arrival_time": booking.arrival_time,
        "data_source": booking.data_source,
        "seats": booking.seats,
        "seat_numbers": booking.seat_numbers,
        "seat_preference": booking.seat_preference,
        "booking_date": booking.booking_date.isoformat(),
        "total_fare": float(booking.total_fare),
        "status": booking.status,
        "created_at": booking.created_at.isoformat() if booking.created_at else None,
        "passenger_name": booking.user.name if booking.user else None,
        "passenger_email": booking.user.email if booking.user else None,
        "receipt_number": build_receipt_number(booking.id, payment.id) if payment else None,
        "ticket_url": f"/ticket/{booking.id}" if booking.status == "CONFIRMED" else None,
        "train": serialize_train_snapshot(booking),
        "payment": serialize_payment(payment),
    }


def get_booking_with_details(db: Session, booking_id: int, user_id: int | None = None) -> Booking:
    query = (
        db.query(Booking)
        .options(joinedload(Booking.user), joinedload(Booking.payment))
        .filter(Booking.id == booking_id)
    )
    if user_id is not None:
        query = query.filter(Booking.user_id == user_id)

    booking = query.first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


def check_availability(selected_train: dict[str, Any], seats: int, preference: str = "No Preference") -> dict:
    seats_left = max(int(selected_train.get("seats_available") or 0), 0)
    total_fare = round(float(selected_train.get("fare_per_seat") or 0) * seats, 2)
    return {
        "available": seats_left >= seats,
        "message": "Seats available" if seats_left >= seats else "Not enough seats available",
        "train_id": selected_train.get("train_id"),
        "train_number": selected_train.get("train_number"),
        "train_name": selected_train.get("train_name"),
        "source": selected_train.get("source"),
        "destination": selected_train.get("destination"),
        "travel_date": selected_train.get("travel_date"),
        "departure_time": selected_train.get("departure_time"),
        "arrival_time": selected_train.get("arrival_time"),
        "seats_requested": seats,
        "seats_left": seats_left,
        "fare_per_seat": round(float(selected_train.get("fare_per_seat") or 0), 2),
        "total_fare": total_fare,
        "seat_preference": preference or "No Preference",
        "data_source": selected_train.get("data_source", "api"),
    }


def _seat_suffix(preference: str) -> str:
    if not preference or preference == "No Preference":
        return ""

    initials = "".join(word[:1].upper() for word in preference.split())
    return f" ({initials})"


def _generate_seat_numbers(seats: int, preference: str) -> str:
    seat_pool = [f"{coach}-{number}" for coach in ["S1", "S2", "S3", "B1", "B2", "A1"] for number in range(1, 73)]
    selected = random.sample(seat_pool, k=seats)
    suffix = _seat_suffix(preference)
    return ", ".join(f"{seat}{suffix}" for seat in selected)


def _coerce_booking_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise HTTPException(status_code=400, detail="Invalid travel date")


def _train_identifier(train_data: dict[str, Any]) -> tuple[Optional[int], Optional[str]]:
    train_id = train_data.get("train_id")
    if train_id in ("", None):
        train_id = None
    elif not isinstance(train_id, int):
        try:
            train_id = int(str(train_id))
        except (TypeError, ValueError):
            train_id = None

    train_number = train_data.get("train_number")
    if train_number in ("", None) and train_id is not None:
        train_number = str(train_id)
    return train_id, str(train_number) if train_number not in (None, "") else None


def create_booking(
    db: Session,
    user_id: int,
    train_data: dict[str, Any],
    seats: int,
    preference: str = "No Preference",
    travel_date: date | None = None,
) -> Booking:
    travel_day = _coerce_booking_date(travel_date or train_data.get("travel_date"))
    if train_data.get("travel_date"):
        selected_day = _coerce_booking_date(train_data["travel_date"])
        if selected_day != travel_day:
            raise HTTPException(status_code=400, detail="Selected train is not available on that date")

    seats_left = int(train_data.get("seats_available") or 0)
    if seats_left and seats_left < seats:
        raise HTTPException(status_code=400, detail="Not enough seats available")

    fare_per_seat = round(float(train_data.get("fare_per_seat") or 0), 2)
    train_id, train_number = _train_identifier(train_data)

    booking = Booking(
        user_id=user_id,
        train_id=train_id,
        train_number=train_number,
        train_name=str(train_data.get("train_name") or "Unknown Train"),
        source=str(train_data.get("source") or ""),
        destination=str(train_data.get("destination") or ""),
        departure_time=train_data.get("departure_time") or "N/A",
        arrival_time=train_data.get("arrival_time") or "N/A",
        data_source=str(train_data.get("data_source") or "api"),
        seats=seats,
        seat_numbers=_generate_seat_numbers(seats, preference),
        seat_preference=preference or "No Preference",
        booking_date=travel_day,
        total_fare=round(seats * fare_per_seat, 2),
        status="PENDING",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


def get_user_bookings(db: Session, user_id: int):
    bookings = (
        db.query(Booking)
        .options(joinedload(Booking.payment), joinedload(Booking.user))
        .filter(Booking.user_id == user_id)
        .order_by(Booking.created_at.desc())
        .all()
    )
    return [serialize_booking(booking) for booking in bookings]
