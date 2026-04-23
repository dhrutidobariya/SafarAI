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
    booking: Optional[dict[str, Any]] = None
    payment_status: Optional[str] = None
    ticket_url: Optional[str] = None
    razorpay_order: Optional[dict[str, Any]] = None
    timestamp: Optional[str] = None


class SelectedTrainIn(BaseModel):
    train_id: Optional[int] = None
    train_number: Optional[str] = None
    train_name: str = Field(min_length=2, max_length=100)
    source: str = Field(min_length=2, max_length=60)
    destination: str = Field(min_length=2, max_length=60)
    travel_date: date
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None
    fare_per_seat: float = Field(ge=0)
    seats_available: Optional[int] = Field(default=None, ge=0)
    data_source: str = "api"


class BookRequest(BaseModel):
    train: SelectedTrainIn
    seats: int = Field(gt=0, le=10)
    seat_preference: str = Field(default="No Preference", max_length=50)


class PaymentRequest(BaseModel):
    booking_id: int
    amount: Optional[float] = Field(default=None, gt=0)


class RazorpayVerificationRequest(BaseModel):
    booking_id: int
    provider: str = "RAZORPAY"
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    razorpay_signature: Optional[str] = None


class TrainOut(BaseModel):
    id: str
    train_id: Optional[int] = None
    train_number: Optional[str] = None
    train_name: str
    source: str
    destination: str
    travel_date: date
    departure_time: str
    arrival_time: str
    seats_available: int
    fare_per_seat: float
    total_fare: Optional[float] = None
    data_source: Optional[str] = None

    class Config:
        from_attributes = True


class PaymentOut(BaseModel):
    id: int
    amount: float
    method: str
    transaction_id: Optional[str]
    status: str
    paid_at: datetime

    class Config:
        from_attributes = True


class BookingOut(BaseModel):
    id: int
    user_id: int
    train_id: Optional[int] = None
    train_number: Optional[str] = None
    train_name: str
    source: str
    destination: str
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None
    data_source: Optional[str] = None
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
