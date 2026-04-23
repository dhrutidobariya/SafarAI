from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import User
from schemas import PaymentRequest, RazorpayVerificationRequest
from services.auth_service import get_current_user
from services.payment_service import create_razorpay_order, verify_payment

router = APIRouter(tags=["payment"])

@router.post("/payment/order")
def create_order(payload: PaymentRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return create_razorpay_order(db, payload.booking_id, user.id)

@router.post("/payment/verify")
def verify_razorpay_payment(payload: RazorpayVerificationRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return verify_payment(
        db,
        payload.booking_id,
        payload.provider,
        payload.razorpay_order_id,
        payload.razorpay_payment_id,
        payload.razorpay_signature,
        user.id,
    )
