import os
from pathlib import Path

from fastapi import HTTPException
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from services.booking_service import build_pnr, build_receipt_number, get_booking_with_details

TICKET_DIR = Path(__file__).resolve().parent.parent / "tickets"


def generate_ticket_pdf(db: Session, booking_id: int, user_id: int | None = None) -> str:
    booking = get_booking_with_details(db, booking_id, user_id)
    if booking.status != "CONFIRMED" or not booking.payment or booking.payment.status != "SUCCESS":
        raise HTTPException(status_code=400, detail="Receipt can be generated only after successful payment")

    TICKET_DIR.mkdir(parents=True, exist_ok=True)
    file_path = TICKET_DIR / f"receipt_{booking_id}.pdf"

    c = canvas.Canvas(str(file_path), pagesize=A4)
    width, height = A4

    def draw_label_value(label: str, value: str, x: float, y: float):
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(colors.HexColor("#475569"))
        c.drawString(x, y, label)
        c.setFont("Helvetica", 10.5)
        c.setFillColor(colors.black)
        c.drawString(x + 120, y, value)

    receipt_number = build_receipt_number(booking.id, booking.payment.id)
    payment_time = booking.payment.paid_at.strftime("%d %b %Y, %I:%M %p")
    created_time = booking.created_at.strftime("%d %b %Y, %I:%M %p")

    c.setFillColor(colors.HexColor("#0f172a"))
    c.rect(0, height - 38 * mm, width, 38 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(18 * mm, height - 18 * mm, "Safar AI Rail Receipt")
    c.setFont("Helvetica", 11)
    c.drawString(18 * mm, height - 26 * mm, "Booking confirmed and payment received")

    c.setFillColor(colors.HexColor("#dcfce7"))
    c.roundRect(width - 62 * mm, height - 28 * mm, 42 * mm, 10 * mm, 4, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#166534"))
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(width - 41 * mm, height - 21.2 * mm, "CONFIRMED")

    c.setFillColor(colors.HexColor("#f8fafc"))
    c.roundRect(15 * mm, height - 108 * mm, width - 30 * mm, 58 * mm, 8, fill=1, stroke=0)
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.roundRect(15 * mm, height - 108 * mm, width - 30 * mm, 58 * mm, 8, fill=0, stroke=1)

    draw_label_value("Passenger", booking.user.name, 22 * mm, height - 60 * mm)
    draw_label_value("Email", booking.user.email, 22 * mm, height - 68 * mm)
    draw_label_value("Booking ID", f"#{booking.id}", 22 * mm, height - 76 * mm)
    draw_label_value("PNR", build_pnr(booking.id), 22 * mm, height - 84 * mm)
    draw_label_value("Receipt No", receipt_number, 22 * mm, height - 92 * mm)
    draw_label_value("Paid On", payment_time, 22 * mm, height - 100 * mm)

    c.setFillColor(colors.white)
    c.roundRect(15 * mm, height - 185 * mm, width - 30 * mm, 66 * mm, 8, fill=1, stroke=0)
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.roundRect(15 * mm, height - 185 * mm, width - 30 * mm, 66 * mm, 8, fill=0, stroke=1)

    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 13)
    c.drawString(22 * mm, height - 128 * mm, "Journey Details")
    c.setFont("Helvetica", 10.5)
    c.drawString(
        22 * mm,
        height - 139 * mm,
        f"{booking.train_name} | {booking.source} to {booking.destination}",
    )
    c.drawString(
        22 * mm,
        height - 148 * mm,
        f"Travel Date: {booking.booking_date.strftime('%d %b %Y')} | Departure: {booking.departure_time or 'N/A'} | Arrival: {booking.arrival_time or 'N/A'}",
    )
    c.drawString(
        22 * mm,
        height - 157 * mm,
        f"Seats: {booking.seats} | Preference: {booking.seat_preference or 'No Preference'}",
    )
    c.drawString(22 * mm, height - 166 * mm, f"Seat Numbers: {booking.seat_numbers or 'Assigned at station'}")
    c.drawString(22 * mm, height - 175 * mm, f"Booked On: {created_time}")

    c.setFillColor(colors.HexColor("#eff6ff"))
    c.roundRect(15 * mm, height - 236 * mm, width - 30 * mm, 36 * mm, 8, fill=1, stroke=0)
    c.setStrokeColor(colors.HexColor("#bfdbfe"))
    c.roundRect(15 * mm, height - 236 * mm, width - 30 * mm, 36 * mm, 8, fill=0, stroke=1)

    draw_label_value("Payment Method", booking.payment.method, 22 * mm, height - 213 * mm)
    draw_label_value("Transaction ID", booking.payment.transaction_id or "N/A", 22 * mm, height - 221 * mm)
    draw_label_value("Amount Paid", f"Rs. {booking.total_fare:,.2f}", 22 * mm, height - 229 * mm)

    c.setFillColor(colors.HexColor("#475569"))
    c.setFont("Helvetica", 9)
    c.drawString(
        15 * mm,
        18 * mm,
        "Please carry a valid ID proof during travel. This receipt is system generated and valid without signature.",
    )

    c.save()
    return os.path.abspath(file_path)
