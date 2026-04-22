from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import Base, SessionLocal, engine
from routes import auth_router, booking_router, chat_router, payment_router, ticket_router, trains_router
from services.seed_service import seed_default_trains

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
app.include_router(chat_router)
app.include_router(trains_router)
app.include_router(booking_router)
app.include_router(payment_router)
app.include_router(ticket_router)


@app.get("/")
def root():
    return {"message": "Railway booking backend running", "mcp_tools_enabled": True}
