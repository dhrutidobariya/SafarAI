import os
from pathlib import Path

from fastapi import HTTPException
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from models import Booking


def generate_ticket_pdf(db: Session, booking_id: int) -> str:
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.status != "CONFIRMED":
        raise HTTPException(status_code=400, detail="Ticket can be generated only after payment")

    ticket_dir = Path("tickets")
    ticket_dir.mkdir(parents=True, exist_ok=True)
    file_path = ticket_dir / f"ticket_{booking_id}.pdf"

    c = canvas.Canvas(str(file_path), pagesize=A4)
    width, height = A4

    # --- Success Banner ---
    banner_height = 50
    banner_y = height - 80
    c.setFillColorRGB(0.92, 0.97, 0.92)  # Light Green background
    c.rect(50, banner_y, width - 100, banner_y + banner_height - (height-80), fill=1, stroke=0)
    
    # Success text
    c.setFillColorRGB(0.13, 0.38, 0.13)  # Dark Green text
    c.setFont("Helvetica-Bold", 14)
    c.drawString(100, banner_y + 18, "Success! ")
    c.setFont("Helvetica", 14)
    c.drawString(165, banner_y + 18, "Thank you for your payment!")

    # --- Content ---
    y_ptr = banner_y - 40
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 12)
    c.drawString(50, y_ptr, f"Dear {booking.user.name.upper()}")
    y_ptr -= 25
    c.drawString(50, y_ptr, "The fee payment has been completed.")
    
    y_ptr -= 40
    
    # Define fields for the receipt
    transaction_date = booking.payment.paid_at.strftime("%b %d, %Y, %I:%M:%S %p") if booking.payment else booking.created_at.strftime("%b %d, %Y, %I:%M:%S %p")
    registration_no = f"Q{booking_id:010d}"
    receipt_no = f"REC{booking_id:04d}{booking.payment.id:04d}" if booking.payment else f"REC{booking_id:08d}"
    
    fields = [
        ("Email Address", f": {booking.user.email}"),
        ("Mobile No", f": 9123456789"), # Placeholder
        ("Registration No", f": {registration_no}"),
        ("Transaction No", f": {booking.payment.transaction_id if booking.payment else 'N/A'}"),
        ("Transaction Date", f": {transaction_date}"),
        ("Bank Ref No", f": {booking.payment.transaction_id if booking.payment else 'N/A'}"),
        ("Reciept No", f": {receipt_no}"),
        ("Amount", f": ₹ {booking.total_fare}"),
        ("Status", ": Paid")
    ]

    # Draw Fields
    c.setFont("Helvetica", 12)
    label_x = 50
    value_x = 180
    
    for label, value in fields:
        c.drawString(label_x, y_ptr, label)
        c.drawString(value_x, y_ptr, value)
        y_ptr -= 20

    # Journey Details (Additional info for clarity)
    y_ptr -= 20
    c.setDash(2, 2)
    c.line(50, y_ptr, width - 50, y_ptr)
    c.setDash(1, 0) # reset
    y_ptr -= 30
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y_ptr, "Journey Details:")
    c.setFont("Helvetica", 11)
    y_ptr -= 20
    c.drawString(50, y_ptr, f"Train: {booking.train.train_name} (#{booking.train.id}) | Seats: {booking.seat_numbers}")
    y_ptr -= 15
    c.drawString(50, y_ptr, f"Route: {booking.train.source} to {booking.train.destination} | Date: {booking.booking_date}")
    
    # --- Footer ---
    y_ptr -= 60
    footer_text1 = f"Your Registration No. {registration_no} is provisionally accepted. Your candidature is subject to"
    footer_text2 = "fulfillment of the prescribed criteria."
    
    c.setFont("Helvetica", 11)
    c.drawString(50, y_ptr, footer_text1)
    y_ptr -= 18
    c.drawString(50, y_ptr, footer_text2)

    c.save()
    return os.path.abspath(file_path)
