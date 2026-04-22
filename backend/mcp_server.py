import os
import uuid
import random
import requests
import datetime
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from db import get_connection

# Load environment variables
load_dotenv()

# RapidAPI configuration
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "indian-railway-irctc.p.rapidapi.com")
RAPIDAPI_TRAIN_ENDPOINT = os.getenv("RAPIDAPI_TRAIN_ENDPOINT", "https://indian-railway-irctc.p.rapidapi.com/api/trains-search")

# Initialize FastMCP server
mcp = FastMCP("Railway Booking MCP Server")

# --- Tool 1: search_trains ---
@mcp.tool()
async def search_trains(source: str, destination: str, travel_date: str, seats: int = 1) -> List[Dict[str, Any]]:
    """
    Search for trains between source and destination on a specific date.
    Combines live data from RapidAPI with local database records.
    """
    results = []
    
    # 1. Call RapidAPI
    try:
        headers = {
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": RAPIDAPI_HOST
        }
        params = {"source": source, "destination": destination}
        response = requests.get(RAPIDAPI_TRAIN_ENDPOINT, headers=headers, params=params, timeout=5)
        
        if response.status_code == 200:
            api_data = response.json()
            if isinstance(api_data, list):
                with get_connection() as conn:
                    cursor = conn.cursor(dictionary=True)
                    for train in api_data:
                        name = train.get("train_name", "Unknown Train")
                        src = train.get("source", source)
                        dest = train.get("destination", destination)
                        fare = float(train.get("fare", 100))
                        seats_avail = train.get("seats_available", 100)
                        dep_time = train.get("departure_time", "09:00")
                        arr_time = train.get("arrival_time", "17:00")

                        # Check if already exists locally
                        check_query = """
                            SELECT id FROM trains 
                            WHERE train_name = %s AND source = %s AND destination = %s AND travel_date = %s
                        """
                        cursor.execute(check_query, (name, src, dest, travel_date))
                        existing = cursor.fetchone()

                        if existing:
                            t_id = existing['id']
                        else:
                            # Insert into local DB
                            insert_query = """
                                INSERT INTO trains (train_name, source, destination, travel_date, departure_time, arrival_time, seats_available, fare_per_seat)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """
                            cursor.execute(insert_query, (name, src, dest, travel_date, dep_time, arr_time, seats_avail, fare))
                            conn.commit()
                            t_id = cursor.lastrowid

                        results.append({
                            "train_id": t_id,
                            "train_name": name,
                            "source": src,
                            "destination": dest,
                            "travel_date": travel_date,
                            "departure_time": dep_time,
                            "arrival_time": arr_time,
                            "seats_available": seats_avail,
                            "fare_per_seat": fare,
                            "total_fare": fare * seats,
                            "data_source": "api"
                        })
    except Exception as e:
        print(f"RapidAPI Error/Sync Error: {e}")
        pass

    # 2. Query Local DB
    try:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT id as train_id, train_name, source, destination, travel_date, 
                       departure_time, arrival_time, seats_available, fare_per_seat
                FROM trains
                WHERE source LIKE %s AND destination LIKE %s 
                AND travel_date = %s AND seats_available >= %s
            """
            cursor.execute(query, (f"%{source}%", f"%{destination}%", travel_date, seats))
            local_trains = cursor.fetchall()
            
            for train in local_trains:
                # Convert date objects to string
                if isinstance(train['travel_date'], (datetime.date, datetime.datetime)):
                    train['travel_date'] = train['travel_date'].strftime('%Y-%m-%d')
                
                train['total_fare'] = float(train['fare_per_seat']) * seats
                train['data_source'] = "local"
                results.append(train)
    except Exception as e:
        print(f"Local DB Error in search_trains: {e}")

    return results

# --- Tool 2: check_seat_availability ---
@mcp.tool()
async def check_seat_availability(train_id: int, seats_requested: int) -> Dict[str, Any]:
    """Check if a specific train has enough seats and get the fare details."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT train_name, seats_available, fare_per_seat FROM trains WHERE id = %s", (train_id,))
            train = cursor.fetchone()
            
            if not train:
                return {"error": "Train not found"}
            
            available = train['seats_available'] >= seats_requested
            fare_per_seat = float(train['fare_per_seat'])
            
            return {
                "available": available,
                "seats_left": train['seats_available'],
                "fare_per_seat": fare_per_seat,
                "total_fare": fare_per_seat * seats_requested,
                "train_name": train['train_name']
            }
    except Exception as e:
        return {"error": f"Database error: {str(e)}"}

# --- Tool 3: create_booking ---
@mcp.tool()
async def create_booking(user_id: int, train_id: int, seats: int, travel_date: str, seat_preference: Optional[str] = None) -> Dict[str, Any]:
    """Create a pending booking for a train."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            conn.start_transaction()
            
            # 1. Row-level lock
            cursor.execute("SELECT seats_available, fare_per_seat FROM trains WHERE id = %s FOR UPDATE", (train_id,))
            train = cursor.fetchone()
            
            if not train:
                conn.rollback()
                return {"error": "Train not found"}
            
            # 2. Check availability
            if train['seats_available'] < seats:
                conn.rollback()
                return {"error": "Not enough seats available"}
            
            # 3. Generate seat numbers
            start_num = 100 - train['seats_available'] + 1 # Simple mock logic
            seat_numbers = ",".join([f"S{start_num + i}" for i in range(seats)])
            
            # 4. Calculate fare
            total_fare = seats * float(train['fare_per_seat'])
            
            # 5. Insert booking
            query = """
                INSERT INTO bookings (user_id, train_id, seats, seat_numbers, seat_preference, booking_date, total_fare, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'PENDING')
            """
            cursor.execute(query, (user_id, train_id, seats, seat_numbers, seat_preference, travel_date, total_fare))
            booking_id = cursor.lastrowid
            
            # 6. Update train seats
            cursor.execute("UPDATE trains SET seats_available = seats_available - %s WHERE id = %s", (seats, train_id))
            
            conn.commit()
            return {
                "success": True,
                "booking_id": booking_id,
                "seat_numbers": seat_numbers,
                "total_fare": total_fare,
                "status": "PENDING"
            }
    except Exception as e:
        return {"error": f"Booking failed: {str(e)}"}

# --- Tool 4: process_payment ---
@mcp.tool()
async def process_payment(booking_id: int, user_id: int, amount: float, method: str = "SIMULATED") -> Dict[str, Any]:
    """Process payment for a pending booking."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            conn.start_transaction()
            
            # 1. Fetch booking
            cursor.execute("SELECT id, total_fare, status, user_id, train_id, seats FROM bookings WHERE id = %s", (booking_id,))
            booking = cursor.fetchone()
            
            if not booking:
                conn.rollback()
                return {"error": "Booking not found"}
            
            # 2. Verify user
            if booking['user_id'] != user_id:
                conn.rollback()
                return {"error": "Unauthorized"}
            
            # 3. Verify status
            if booking['status'] != 'PENDING':
                conn.rollback()
                return {"error": f"Booking is not in PENDING state (Current: {booking['status']})"}
            
            # 4. Verify amount
            if abs(amount - float(booking['total_fare'])) > 0.01:
                conn.rollback()
                return {"error": "Amount mismatch"}
            
            # 5. Simulate Payment
            transaction_id = "TXN_" + uuid.uuid4().hex[:10].upper()
            payment_success = random.random() < 0.92
            
            payment_status = 'SUCCESS' if payment_success else 'FAILED'
            booking_status = 'CONFIRMED' if payment_success else 'CANCELLED'
            
            # 6. Insert payment record
            cursor.execute(
                "INSERT INTO payments (booking_id, amount, method, transaction_id, status) VALUES (%s, %s, %s, %s, %s)",
                (booking_id, amount, method, transaction_id, payment_status)
            )
            
            # 7 & 8. Update booking and train if failed
            cursor.execute("UPDATE bookings SET status = %s WHERE id = %s", (booking_status, booking_id))
            
            if not payment_success:
                cursor.execute("UPDATE trains SET seats_available = seats_available + %s WHERE id = %s", 
                               (booking['seats'], booking['train_id']))
            
            conn.commit()
            return {
                "success": payment_success,
                "transaction_id": transaction_id,
                "payment_status": payment_status,
                "booking_status": booking_status,
                "message": "Payment processed successfully" if payment_success else "Payment failed"
            }
    except Exception as e:
        return {"error": f"Payment error: {str(e)}"}

# --- Tool 5: get_booking_history ---
@mcp.tool()
async def get_booking_history(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieve booking history for a user."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT b.id, b.seats, b.seat_numbers, b.booking_date, b.total_fare, b.status, b.created_at,
                       t.train_name, t.source, t.destination, t.departure_time, t.arrival_time,
                       p.transaction_id, p.status as payment_status, p.paid_at
                FROM bookings b
                JOIN trains t ON b.train_id = t.id
                LEFT JOIN payments p ON p.booking_id = b.id
                WHERE b.user_id = %s
                ORDER BY b.created_at DESC
                LIMIT %s
            """
            cursor.execute(query, (user_id, limit))
            history = cursor.fetchall()
            
            for item in history:
                # Convert dates/times to strings
                for key in ['booking_date', 'created_at', 'paid_at']:
                    if item.get(key) and isinstance(item[key], (datetime.date, datetime.datetime)):
                        item[key] = item[key].isoformat()
                item['total_fare'] = float(item['total_fare'])
            
            return history
    except Exception as e:
        return [{"error": f"Failed to fetch history: {str(e)}"}]

# --- Tool 6: cancel_booking ---
@mcp.tool()
async def cancel_booking(booking_id: int, user_id: int) -> Dict[str, Any]:
    """Cancel a confirmed booking."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            conn.start_transaction()
            
            # 1. Fetch booking
            cursor.execute("SELECT user_id, train_id, seats, status, booking_date, total_fare FROM bookings WHERE id = %s", (booking_id,))
            booking = cursor.fetchone()
            
            if not booking:
                conn.rollback()
                return {"error": "Booking not found"}
            
            # 2. Verify user
            if booking['user_id'] != user_id:
                conn.rollback()
                return {"error": "Unauthorized"}
            
            # 3. Verify status
            if booking['status'] != 'CONFIRMED':
                conn.rollback()
                return {"error": "Only confirmed bookings can be cancelled"}
            
            # 4. Verify date
            if booking['booking_date'] <= datetime.date.today():
                conn.rollback()
                return {"error": "Cannot cancel past or same-day travel"}
            
            # 5. Update status
            cursor.execute("UPDATE bookings SET status = 'CANCELLED' WHERE id = %s", (booking_id,))
            
            # 6. Restore seats
            cursor.execute("UPDATE trains SET seats_available = seats_available + %s WHERE id = %s", 
                           (booking['seats'], booking['train_id']))
            
            conn.commit()
            return {
                "success": True,
                "message": "Booking cancelled successfully",
                "refund_note": f"Refund of ₹{float(booking['total_fare'])} will be processed in 5-7 business days"
            }
    except Exception as e:
        return {"error": f"Cancellation failed: {str(e)}"}

# --- Tool 7: save_chat_message ---
@mcp.tool()
async def save_chat_message(user_id: int, role: str, message: str, is_tool_message: bool = False) -> Dict[str, Any]:
    """Save a chat message to history."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            query = "INSERT INTO chat_history (user_id, role, message, is_tool_message) VALUES (%s, %s, %s, %s)"
            cursor.execute(query, (user_id, role, message, is_tool_message))
            chat_id = cursor.lastrowid
            conn.commit()
            return {"saved": True, "chat_id": chat_id}
    except Exception as e:
        return {"error": f"Failed to save message: {str(e)}"}

# --- Tool 8: get_chat_history ---
@mcp.tool()
async def get_chat_history(user_id: int, limit: int = 12) -> List[Dict[str, Any]]:
    """Retrieve recent chat history for context."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT role, message, is_tool_message, created_at 
                FROM chat_history 
                WHERE user_id = %s 
                ORDER BY created_at DESC 
                LIMIT %s
            """
            cursor.execute(query, (user_id, limit))
            history = cursor.fetchall()
            
            # Format and reverse
            formatted_history = []
            for msg in history:
                formatted_history.append({
                    "role": msg['role'],
                    "content": msg['message'],
                    "is_tool": bool(msg['is_tool_message']),
                    "timestamp": msg['created_at'].isoformat() if msg['created_at'] else None
                })
            
            return formatted_history[::-1] # Oldest first
    except Exception as e:
        print(f"Chat history error: {e}")
        return []

if __name__ == "__main__":
    mcp.run()
