from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(120), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    bookings = relationship("Booking", back_populates="user")
    chats = relationship("ChatHistory", back_populates="user")


class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    train_id = Column(Integer, nullable=True, index=True)
    train_number = Column(String(50), nullable=True, index=True)
    train_name = Column(String(100), nullable=False)
    source = Column(String(60), nullable=False, index=True)
    destination = Column(String(60), nullable=False, index=True)
    departure_time = Column(String(20), nullable=True)
    arrival_time = Column(String(20), nullable=True)
    data_source = Column(String(20), nullable=True)
    seats = Column(Integer, nullable=False)
    seat_numbers = Column(String(255), nullable=True)
    seat_preference = Column(String(50), nullable=True)
    booking_date = Column(Date, nullable=False)
    total_fare = Column(Float, nullable=False)
    status = Column(String(30), default="PENDING")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="bookings")
    payment = relationship("Payment", back_populates="booking", uselist=False)


class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), unique=True, nullable=False)
    amount = Column(Float, nullable=False)
    method = Column(String(30), default="SIMULATED")
    transaction_id = Column(String(120), nullable=True)
    status = Column(String(20), nullable=False)
    paid_at = Column(DateTime, default=datetime.utcnow)

    booking = relationship("Booking", back_populates="payment")


class ChatHistory(Base):
    __tablename__ = "chat_history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_tool_message = Column(Boolean, default=False)

    user = relationship("User", back_populates="chats")
