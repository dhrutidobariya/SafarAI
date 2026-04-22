from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import User
from schemas import PaymentRequest
from services.auth_service import get_current_user
from services.payment_service import process_payment

router = APIRouter(tags=["payment"])


@router.post("/payment")
def payment(payload: PaymentRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    payment_row = process_payment(db, payload.booking_id, payload.amount)
    return {"status": payment_row.status, "transaction_id": payment_row.transaction_id}
