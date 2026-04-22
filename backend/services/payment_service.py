import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import Booking, Payment


def process_payment(db: Session, booking_id: int, amount: float) -> Payment:
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if amount < booking.total_fare:
        raise HTTPException(status_code=400, detail="Payment failure: insufficient amount")

    existing = db.query(Payment).filter(Payment.booking_id == booking_id).first()
    if existing and existing.status == "SUCCESS":
        return existing

    payment = existing or Payment(booking_id=booking_id, amount=amount)
    payment.status = "SUCCESS"
    payment.transaction_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"
    payment.method = "SIMULATED"
    booking.status = "CONFIRMED"
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment
