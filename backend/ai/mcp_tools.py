from datetime import date

from sqlalchemy.orm import Session

from services.booking_service import check_availability, create_booking, search_trains
from services.payment_service import process_payment
from services.ticket_service import generate_ticket_pdf


class MCPToolRegistry:
    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self.tools = {
            "search_trains": self.search_trains,
            "check_availability": self.check_availability,
            "book_ticket": self.book_ticket,
            "process_payment": self.process_payment,
            "generate_ticket": self.generate_ticket,
        }

    def search_trains(self, source: str, destination: str, travel_date: str):
        parsed_date = date.fromisoformat(travel_date)
        trains = search_trains(self.db, source, destination, parsed_date)
        return [
            {
                "id": t.id,
                "train_name": t.train_name,
                "source": t.source,
                "destination": t.destination,
                "travel_date": str(t.travel_date),
                "departure_time": t.departure_time,
                "arrival_time": t.arrival_time,
                "seats_available": t.seats_available,
                "fare_per_seat": t.fare_per_seat,
            }
            for t in trains
        ]

    def check_availability(self, train_id: int, seats: int):
        return check_availability(self.db, train_id, seats)

    def book_ticket(self, user_id: int, train_id: int, seats: int, preference: str = "No Preference"):
        booking = create_booking(self.db, user_id, train_id, seats, preference)
        return {"booking_id": booking.id, "total_fare": booking.total_fare, "status": booking.status}

    def process_payment(self, booking_id: int, amount: float):
        payment = process_payment(self.db, booking_id, amount)
        return {"status": payment.status, "transaction_id": payment.transaction_id}

    def generate_ticket(self, booking_id: int):
        path = generate_ticket_pdf(self.db, booking_id)
        return {"ticket_path": path}

    def call(self, name: str, args: dict):
        if name not in self.tools:
            raise ValueError(f"Unknown MCP tool: {name}")
        return self.tools[name](**args)


TOOL_DEFINITIONS = [
    {"name": "search_trains", "description": "Search trains by source, destination and date", "parameters": ["source", "destination", "travel_date"]},
    {"name": "check_availability", "description": "Check if seats are available in a train", "parameters": ["train_id", "seats"]},
    {"name": "book_ticket", "description": "Create booking in pending state", "parameters": ["user_id", "train_id", "seats", "preference"]},
    {"name": "process_payment", "description": "Process payment for booking", "parameters": ["booking_id", "amount"]},
    {"name": "generate_ticket", "description": "Generate PDF ticket for paid booking", "parameters": ["booking_id"]},
]
