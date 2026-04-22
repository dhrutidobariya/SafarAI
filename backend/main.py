from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import Base, SessionLocal, engine
from routes import auth_router, booking_router, payment_router, ticket_router, trains_router
from chatbot import router as chatbot_router
from services.seed_service import seed_default_trains
from services.auth_service import get_current_user
from fastapi import Depends, HTTPException

Base.metadata.create_all(bind=engine)

db = SessionLocal()
try:
    seed_default_trains(db)
finally:
    db.close()

app = FastAPI(title="Railway MCP Booking API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chatbot_router)
app.include_router(trains_router)
app.include_router(booking_router)
app.include_router(payment_router)
app.include_router(ticket_router)


@app.get("/")
def root():
    return {"message": "Railway booking backend running", "mcp_tools_enabled": True}

# New endpoint for ticket details (used by frontend for PDF generation)
@app.get("/api/booking/{booking_id}")
async def get_booking_detail(booking_id: int, current_user: dict = Depends(get_current_user)):
    from db import get_connection
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT b.id, b.seats, b.seat_numbers, b.seat_preference,
                   b.booking_date, b.total_fare, b.status, b.created_at,
                   t.train_name, t.source, t.destination,
                   t.departure_time, t.arrival_time,
                   u.name as passenger_name, u.email,
                   p.transaction_id, p.status as payment_status, p.paid_at
            FROM bookings b
            JOIN trains t ON b.train_id = t.id
            JOIN users u ON b.user_id = u.id
            LEFT JOIN payments p ON p.booking_id = b.id
            WHERE b.id = %s AND b.user_id = %s
        """, (booking_id, current_user["id"]))
        booking = cursor.fetchone()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking
