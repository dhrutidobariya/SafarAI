from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import Base, engine, get_db
from models import User
from routes import auth_router, booking_router, chat_router, payment_router, ticket_router, trains_router
from services.auth_service import get_current_user
from services.booking_service import get_booking_with_details, serialize_booking
from services.schema_service import upgrade_runtime_schema

Base.metadata.create_all(bind=engine)
upgrade_runtime_schema(engine)

app = FastAPI(title="Railway Booking API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(trains_router)
app.include_router(booking_router)
app.include_router(payment_router)
app.include_router(ticket_router)


@app.get("/")
def root():
    return {"message": "Railway booking backend running", "train_search_mode": "rapidapi-live"}


@app.get("/api/booking/{booking_id}")
@app.get("/booking/{booking_id}")
def get_booking_detail(
    booking_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    booking = get_booking_with_details(db, booking_id, current_user.id)
    return serialize_booking(booking)
