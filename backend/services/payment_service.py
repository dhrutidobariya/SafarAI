import os
import hmac
import hashlib
import razorpay
from fastapi import HTTPException
from sqlalchemy.orm import Session
from models import Booking, Payment
from dotenv import load_dotenv

load_dotenv()

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

def create_razorpay_order(db: Session, booking_id: int):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    # Amount is in paise for Razorpay
    amount_in_paise = int(booking.total_fare * 100)
    
    data = {
        "amount": amount_in_paise,
        "currency": "INR",
        "receipt": f"receipt_{booking_id}",
        "payment_capture": 1
    }
    
    try:
        order = client.order.create(data=data)
        return {
            "order_id": order["id"],
            "amount": booking.total_fare,
            "currency": "INR",
            "key": RAZORPAY_KEY_ID
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Razorpay Order Error: {str(e)}")

def verify_payment(db: Session, booking_id: int, razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str):
    # Verify the payment signature
    params_dict = {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_payment_id': razorpay_payment_id,
        'razorpay_signature': razorpay_signature
    }
    
    try:
        client.utility.verify_payment_signature(params_dict)
        
        # If verification succeeds, update DB
        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        # Create or update payment record
        payment = db.query(Payment).filter(Payment.booking_id == booking_id).first()
        if not payment:
            payment = Payment(booking_id=booking_id)
        
        payment.amount = booking.total_fare
        payment.method = "RAZORPAY"
        payment.transaction_id = razorpay_payment_id
        payment.status = "SUCCESS"
        
        booking.status = "CONFIRMED"
        
        db.add(payment)
        db.commit()
        db.refresh(payment)
        
        return {"status": "SUCCESS", "booking_id": booking_id}
    except Exception as e:
        # If signature verification fails
        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if booking:
            booking.status = "CANCELLED"
            db.commit()
        raise HTTPException(status_code=400, detail="Invalid Payment Signature")
