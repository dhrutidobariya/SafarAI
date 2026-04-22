from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=6, max_length=100)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    name: str


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[dict[str, Any]]
    booking_id: Optional[int] = None
    payment_status: Optional[str] = None
    ticket_url: Optional[str] = None
    timestamp: Optional[str] = None


class BookRequest(BaseModel):
    train_id: int
    seats: int = Field(gt=0, le=10)
    date: date


class PaymentRequest(BaseModel):
    booking_id: int
    amount: float = Field(gt=0)


class RazorpayVerificationRequest(BaseModel):
    booking_id: int
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class TrainOut(BaseModel):
    id: int
    train_name: str
    source: str
    destination: str
    travel_date: date
    departure_time: str
    arrival_time: str
    seats_available: int
    fare_per_seat: float

    class Config:
        from_attributes = True


class PaymentOut(BaseModel):
    id: int
    amount: float
    transaction_id: Optional[str]
    status: str
    paid_at: datetime

    class Config:
        from_attributes = True


class BookingOut(BaseModel):
    id: int
    user_id: int
    train_id: int
    seats: int
    seat_numbers: Optional[str] = None
    seat_preference: Optional[str] = None
    booking_date: date
    total_fare: float
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class BookingHistoryOut(BookingOut):
    train: TrainOut
    payment: Optional[PaymentOut] = None

    class Config:
        from_attributes = True
