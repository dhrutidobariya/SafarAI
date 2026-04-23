import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import razorpay
from dotenv import load_dotenv
from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import Payment
from services.booking_service import get_booking_with_details, serialize_booking

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")


def is_razorpay_configured() -> bool:
    return bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)


def get_razorpay_client():
    if not is_razorpay_configured():
        raise HTTPException(status_code=500, detail="Razorpay is not configured on the backend")
    return razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


def _ticket_url(booking_id: int) -> str:
    return f"/ticket/{booking_id}"


def _demo_order(booking_id: int, amount: float, message: str) -> dict:
    return {
        "provider": "SIMULATED",
        "order_id": f"demo_order_{booking_id}_{uuid4().hex[:10]}",
        "amount": amount,
        "currency": "INR",
        "message": message,
        "mode": "demo",
    }


def _payment_success_response(
    db: Session,
    booking_id: int,
    provider: str,
    transaction_id: str,
    user_id: int | None = None,
) -> dict:
    booking = get_booking_with_details(db, booking_id, user_id)
    payment = booking.payment or Payment(booking_id=booking.id, amount=booking.total_fare, status="SUCCESS")

    payment.amount = booking.total_fare
    payment.method = provider
    payment.transaction_id = transaction_id
    payment.status = "SUCCESS"
    payment.paid_at = datetime.utcnow()

    booking.status = "CONFIRMED"

    db.add(payment)
    db.add(booking)
    db.commit()

    confirmed_booking = get_booking_with_details(db, booking_id, booking.user_id)
    confirmed_payment = confirmed_booking.payment

    return {
        "status": "SUCCESS",
        "payment_status": "SUCCESS",
        "booking_id": confirmed_booking.id,
        "transaction_id": confirmed_payment.transaction_id if confirmed_payment else transaction_id,
        "payment_method": confirmed_payment.method if confirmed_payment else provider,
        "ticket_url": _ticket_url(confirmed_booking.id),
        "booking": serialize_booking(confirmed_booking),
    }


def create_razorpay_order(db: Session, booking_id: int, user_id: int | None = None):
    booking = get_booking_with_details(db, booking_id, user_id)

    if booking.status == "CONFIRMED" and booking.payment and booking.payment.status == "SUCCESS":
        return {
            "provider": booking.payment.method,
            "status": "ALREADY_PAID",
            "amount": booking.total_fare,
            "currency": "INR",
            "message": "This booking is already confirmed.",
            "ticket_url": _ticket_url(booking.id),
        }

    amount_in_paise = int(round(booking.total_fare * 100))
    data = {
        "amount": amount_in_paise,
        "currency": "INR",
        "receipt": f"receipt_{booking_id}",
        "payment_capture": 1,
    }

    if not is_razorpay_configured():
        return _demo_order(
            booking.id,
            booking.total_fare,
            "Demo payment mode is active because Razorpay keys are not configured.",
        )

    try:
        client = get_razorpay_client()
        order = client.order.create(data=data)
        return {
            "provider": "RAZORPAY",
            "order_id": order["id"],
            "amount": booking.total_fare,
            "currency": "INR",
            "key": RAZORPAY_KEY_ID,
        }
    except HTTPException:
        raise
    except Exception:
        return _demo_order(
            booking.id,
            booking.total_fare,
            "Live Razorpay checkout is unavailable right now, so demo payment mode has been enabled.",
        )


def verify_payment(
    db: Session,
    booking_id: int,
    provider: str = "RAZORPAY",
    razorpay_order_id: str | None = None,
    razorpay_payment_id: str | None = None,
    razorpay_signature: str | None = None,
    user_id: int | None = None,
):
    normalized_provider = (provider or "RAZORPAY").upper()

    if normalized_provider == "SIMULATED":
        return _payment_success_response(
            db,
            booking_id,
            "SIMULATED",
            razorpay_payment_id or f"demo_pay_{uuid4().hex[:12]}",
            user_id,
        )

    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        raise HTTPException(status_code=400, detail="Missing Razorpay payment details")

    params_dict = {
        "razorpay_order_id": razorpay_order_id,
        "razorpay_payment_id": razorpay_payment_id,
        "razorpay_signature": razorpay_signature,
    }

    try:
        client = get_razorpay_client()
        client.utility.verify_payment_signature(params_dict)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid payment signature") from exc

    return _payment_success_response(db, booking_id, "RAZORPAY", razorpay_payment_id, user_id)
