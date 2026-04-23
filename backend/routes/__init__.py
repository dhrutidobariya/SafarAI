from routes.auth import router as auth_router
from routes.booking import router as booking_router
from routes.chat import router as chat_router
from routes.payment import router as payment_router
from routes.ticket import router as ticket_router
from routes.trains import router as trains_router

__all__ = [
    "auth_router",
    "trains_router",
    "booking_router",
    "chat_router",
    "payment_router",
    "ticket_router",
]
