import re
import os
import json
import asyncio
from datetime import date, timedelta, datetime
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request
from openai import AsyncOpenAI
from dotenv import load_dotenv

from services.auth_service import get_current_user
# Import tools from mcp_server
from mcp_server import (
    search_trains, 
    check_seat_availability, 
    create_booking, 
    process_payment, 
    get_booking_history, 
    cancel_booking, 
    save_chat_message, 
    get_chat_history
)

load_dotenv()

router = APIRouter(tags=["chatbot"])

# --- Step 1: Rule-based intent classifier ---

INTENT_PATTERNS = {
    "search_trains": {
        "keywords": ["book", "ticket", "train", "travel", "journey", "from", "to", "search", "find", "available", "seats"],
        "patterns": [
            r"from\s+(\w[\w\s]*)\s+to\s+(\w[\w\s]*)",
            r"book\s+(\d+)\s+(?:ticket|seat)",
            r"train.*?(tomorrow|today|\d{4}-\d{2}-\d{2})"
        ]
    },
    "booking_history": {
        "keywords": ["history", "my booking", "my ticket", "past", "previous", "show booking", "booked"],
        "patterns": [r"(my|show|view|check)\s+(booking|ticket)s?"]
    },
    "cancel_booking": {
        "keywords": ["cancel", "cancellation", "refund", "cancel booking"],
        "patterns": [r"cancel\s+(?:booking\s+)?#?(\d+)"]
    },
    "payment": {
        "keywords": ["pay", "payment", "confirm", "proceed", "razorpay"],
        "patterns": [r"pay\s+(?:₹|rs\.?)?\s*[\d,]+"]
    },
    "greeting": {
        "keywords": ["hi", "hello", "hey", "start", "help", "what can you do"],
        "patterns": []
    },
    "yes_confirm": {
        "keywords": ["yes", "yeah", "yep", "confirm", "ok", "okay", "sure", "proceed", "book it", "go ahead", "pay now", "make payment"],
        "patterns": [r"^\s*(yes|y|ok|okay|sure|confirm|proceed|pay|make payment)\b"]
    },
    "no_decline": {
        "keywords": ["no", "nope", "cancel", "don't", "dont", "stop", "nevermind", "back"],
        "patterns": []
    }
}

def classify_intent(message: str) -> Tuple[str, float]:
    """Returns (intent_name, confidence_score 0.0-1.0)"""
    message_lower = message.lower()
    scores = {}
    for intent, data in INTENT_PATTERNS.items():
        keyword_hits = sum(1 for kw in data["keywords"] if kw in message_lower)
        keyword_score = min(keyword_hits / max(len(data["keywords"]) * 0.3, 1), 1.0)
        pattern_hits = sum(1 for p in data["patterns"] if re.search(p, message_lower))
        pattern_score = min(pattern_hits * 0.4, 1.0)
        scores[intent] = keyword_score * 0.6 + pattern_score * 0.4
    
    best_intent = max(scores, key=scores.get)
    return best_intent, scores[best_intent]

# --- Step 2: Entity extractor ---

def extract_entities(message: str) -> Dict[str, Any]:
    """Extract booking entities from message without calling LLM"""
    entities = {}
    
    # Extract source and destination
    route_match = re.search(r"from\s+([A-Za-z][\w\s]{2,20}?)\s+to\s+([A-Za-z][\w\s]{2,20}?)(?:\s|$|on|for|tomorrow|today)", message, re.IGNORECASE)
    if route_match:
        entities["source"] = route_match.group(1).strip()
        entities["destination"] = route_match.group(2).strip()
    
    # Extract seats
    seats_match = re.search(r"(\d+)\s+(?:seat|ticket|passenger|person)", message, re.IGNORECASE)
    if seats_match:
        entities["seats"] = int(seats_match.group(1))
    else:
        entities["seats"] = 1
    
    # Extract date
    today = date.today()
    if "tomorrow" in message.lower():
        entities["travel_date"] = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    elif "today" in message.lower():
        entities["travel_date"] = today.strftime("%Y-%m-%d")
    else:
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", message)
        if date_match:
            entities["travel_date"] = date_match.group(1)
        else:
            entities["travel_date"] = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    
    # Extract seat preference
    if any(w in message.lower() for w in ["window", "aisle", "lower", "upper", "middle"]):
        for pref in ["window", "aisle", "lower", "upper", "middle"]:
            if pref in message.lower():
                entities["seat_preference"] = pref
                break
    
    # Extract booking_id
    bid_match = re.search(r"(?:booking|id|#)\s*(\d+)", message, re.IGNORECASE)
    if bid_match:
        entities["booking_id"] = int(bid_match.group(1))
    
    return entities

# --- Step 3: Session state machine ---

class BookingState(str, Enum):
    IDLE = "IDLE"
    SEARCHING = "SEARCHING"
    AWAITING_TRAIN_SELECTION = "AWAITING_TRAIN_SELECTION"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    COMPLETED = "COMPLETED"

sessions: Dict[int, Dict[str, Any]] = {}

def get_session(user_id: int) -> Dict[str, Any]:
    if user_id not in sessions:
        sessions[user_id] = {
            "state": BookingState.IDLE,
            "pending_search": None,
            "search_results": None,
            "pending_booking": None,
            "confirmed_booking_id": None,
            "confirmed_total_fare": None,
            "llm_call_count": 0,
            "last_reset": datetime.utcnow()
        }
    return sessions[user_id]

# --- Step 4: OpenAI function definitions ---

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_trains",
            "description": "Search for available trains between two stations on a given date. Always call this before booking.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Departure station name"},
                    "destination": {"type": "string", "description": "Arrival station name"},
                    "travel_date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                    "seats": {"type": "integer", "description": "Number of seats needed", "default": 1}
                },
                "required": ["source", "destination", "travel_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_seat_availability",
            "description": "Check real-time seat availability for a specific train by its train_id",
            "parameters": {
                "type": "object",
                "properties": {
                    "train_id": {"type": "integer"},
                    "seats_requested": {"type": "integer"}
                },
                "required": ["train_id", "seats_requested"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_booking_history",
            "description": "Get the user's past and current bookings",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 10}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_booking",
            "description": "Cancel a confirmed booking by booking ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_id": {"type": "integer", "description": "The booking ID to cancel"}
                },
                "required": ["booking_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "initialize_payment",
            "description": "Call this when the user says YES to payment for a pending booking.",
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_id": {"type": "integer"}
                },
                "required": ["booking_id"]
            }
        }
    }
]

# --- Step 5: LLM System Prompt ---

SYSTEM_PROMPT = """You are RailBot, a smart and friendly AI assistant for an Indian railway ticket booking system.

## Your capabilities
You help users: search trains, check seat availability, book tickets, process payments, view booking history, and cancel bookings.

## Tools available to you
- search_trains: Search trains between stations. Use this whenever a user asks about trains or wants to book.
- check_seat_availability: Verify seats are still available before confirming to user.
- get_booking_history: Show user's past bookings.
- cancel_booking: Cancel a booking by ID.
- initialize_payment: MUST call this when the user says YES to payment for a pending booking.

## Tools you must NOT call (handled by system)
- create_booking: The booking system handles this after user confirmation. Never call it yourself.
- process_payment: The payment system handles this. Never call it yourself.

## Strict behavioral rules
1. NEVER invent train names, timings, seat counts, or fares. Always call search_trains first.
2. After search_trains returns results, present them clearly:
   - Show train name, departure \u2192 arrival time, fare per seat, seats available
   - If multiple trains, number them: "1. Rajdhani Express..."
   - Ask: "Which train would you like? Reply with the number or train name."
3. After user selects a train, confirm details BEFORE booking:
   "Got it! Here's your booking summary:
    Train: [name]
    Route: [source] \u2192 [destination]  
    Date: [date]
    Seats: [N]
    Total Fare: \u20b9[amount]
    Reply YES to confirm and proceed to payment, or NO to cancel."
4. Never book or charge without explicit YES confirmation.
5. For payment, after create_booking succeeds (system does this), ask:
   "Your booking #[id] is created. Total: \u20b9[fare]. Shall I process payment now? (Payment method: Razorpay Secure Checkout)"
6. Keep responses under 200 words unless showing a list of trains.
7. Format money as \u20b9X,XXX (Indian format).
8. If the user's message is unclear or gibberish, politely ask them to clarify or tell them what you can do.
9. If user asks anything unrelated to railway booking, answer briefly if you can, but then steer them back: "While I can chat about that briefly, I'm specialized for railway bookings. How can I help you book a ticket today?"
10. Always be warm and helpful. Use simple English.
11. If search returns no trains: "No trains found for [route] on [date]. Would you like to try a different date?"
12. NEVER say "Payment successful" or "Booking confirmed" after the user says YES to payment. Just say "Opening secure payment gateway..." and let the system handle it.

## Current user context
Name: {user_name}
User ID: {user_id}
Current date: {today}
Session state: {state}
"""

# --- Step 6: Main chat handler ---

@router.post("/chat")
async def chat_endpoint(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    body = await request.json()
    message = body.get("message", "").strip()
    if not message:
        return {"response": "I didn't receive any message. How can I help you?"}
        
    user_id = current_user["id"]
    user_name = current_user["name"]
    
    session = get_session(user_id)
    
    # Rate limit check
    if session["llm_call_count"] > 30:
        if (datetime.utcnow() - session["last_reset"]).seconds > 3600:
            session["llm_call_count"] = 0
            session["last_reset"] = datetime.utcnow()
        else:
            return {"response": "You've reached the hourly limit. Please try again in a bit.", "state": session["state"]}
    
    # Save user message
    await save_chat_message(user_id, "user", message, False)
    
    intent, confidence = classify_intent(message)
    
    # --- State Machine Path ---
    if session["state"] == BookingState.AWAITING_CONFIRMATION:
        if intent == "yes_confirm":
            pb = session["pending_booking"]
            result = await create_booking(
                user_id=user_id,
                train_id=pb["train_id"],
                seats=pb["seats"],
                seat_preference=pb.get("seat_preference"),
                travel_date=pb["travel_date"]
            )
            if "error" not in result:
                session["state"] = BookingState.AWAITING_PAYMENT
                session["confirmed_booking_id"] = result["booking_id"]
                session["confirmed_total_fare"] = result["total_fare"]
                response = f"Booking created! \ud83c\udf89\nBooking ID: #{result['booking_id']}\nSeats: {result['seat_numbers']}\nTotal: \u20b9{result['total_fare']:,.0f}\n\nShall I process payment now? Type YES to pay or NO to cancel."
            else:
                session["state"] = BookingState.IDLE
                response = f"Sorry, booking failed: {result.get('error')}. Please try searching again."
            await save_chat_message(user_id, "assistant", response, False)
            return {"response": response, "state": session["state"], "booking_id": result.get("booking_id")}
        
        elif intent == "no_decline":
            session["state"] = BookingState.IDLE
            session["pending_booking"] = None
            response = "Booking cancelled. No worries! Let me know if you'd like to search for other trains."
            await save_chat_message(user_id, "assistant", response, False)
            return {"response": response, "state": session["state"]}
    
    if session["state"] == BookingState.AWAITING_PAYMENT:
        if intent == "yes_confirm":
            bid = session["confirmed_booking_id"]
            fare = session["confirmed_total_fare"]
            
            # Create Razorpay Order
            from database import SessionLocal
            db = SessionLocal()
            try:
                from services.payment_service import create_razorpay_order
                order_data = create_razorpay_order(db, bid)
                
                response = f"Opening secure payment gateway for Booking #{bid}. Please complete the payment in the popup."
                await save_chat_message(user_id, "assistant", response, False)
                return {
                    "response": response, 
                    "state": session["state"], 
                    "razorpay_order": order_data,
                    "booking_id": bid
                }
            except Exception as e:
                response = f"Sorry, I couldn't initialize the payment: {str(e)}"
                await save_chat_message(user_id, "assistant", response, False)
                return {"response": response, "state": session["state"]}
            finally:
                db.close()

    # --- LLM Path ---
    history = await get_chat_history(user_id, limit=12)
    today = date.today().strftime("%Y-%m-%d")
    
    system = SYSTEM_PROMPT.format(
        user_name=user_name,
        user_id=user_id,
        today=today,
        state=session["state"]
    )
    
    messages = [{"role": "system", "content": system}]
    for h in history:
        if not h.get("is_tool", False):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": message})
    
    session["llm_call_count"] += 1
    
    response_text = await run_llm_with_tools(messages, session, user_id)
    
    await save_chat_message(user_id, "assistant", response_text, False)
    return {
        "response": response_text,
        "state": session["state"],
        "booking_id": session.get("confirmed_booking_id"),
        "razorpay_order": session.pop("razorpay_order_from_tool", None)
    }

# --- Step 7: LLM tool execution loop ---

async def run_llm_with_tools(messages: list, session: dict, user_id: int) -> str:
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    TOOL_MAP = {
        "search_trains": search_trains,
        "check_seat_availability": check_seat_availability,
        "get_booking_history": get_booking_history,
        "cancel_booking": cancel_booking,
        "initialize_payment": None # Handled below
    }
    
    for iteration in range(4):
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=OPENAI_TOOLS,
            tool_choice="auto",
            temperature=0.3,
            max_tokens=600
        )
        
        choice = response.choices[0]
        
        if choice.finish_reason == "stop" or not choice.message.tool_calls:
            final_text = choice.message.content or "I couldn't process that. Please try again."
            
            # State detection from text
            if "reply yes to confirm" in final_text.lower() and session["state"] in [BookingState.IDLE, BookingState.SEARCHING, BookingState.AWAITING_TRAIN_SELECTION]:
                session["state"] = BookingState.AWAITING_CONFIRMATION
            
            return final_text
        
        # Tool call handling
        messages.append(choice.message)
        
        for tool_call in choice.message.tool_calls:
            func_name = tool_call.function.name
            func_args = json.loads(tool_call.function.arguments)
            
            if func_name in ["get_booking_history", "cancel_booking"]:
                func_args["user_id"] = user_id
            
            if func_name == "initialize_payment":
                from database import SessionLocal
                from services.payment_service import create_razorpay_order
                db = SessionLocal()
                try:
                    order_data = create_razorpay_order(db, func_args["booking_id"])
                    session["razorpay_order_from_tool"] = order_data
                    tool_result_str = json.dumps({"status": "success", "message": "Razorpay order created. System will now open the payment popup."})
                except Exception as e:
                    tool_result_str = json.dumps({"error": str(e)})
                finally:
                    db.close()
            
            elif func_name in TOOL_MAP and TOOL_MAP[func_name]:
                try:
                    # Handle both sync and async functions if needed
                    func = TOOL_MAP[func_name]
                    if asyncio.iscoroutinefunction(func):
                        result = await func(**func_args)
                    else:
                        result = func(**func_args)
                    
                    if func_name == "search_trains":
                        session["search_results"] = result
                        session["state"] = BookingState.AWAITING_TRAIN_SELECTION
                        if len(result) == 1:
                            t = result[0]
                            session["pending_booking"] = {
                                "train_id": t["train_id"],
                                "train_name": t["train_name"],
                                "seats": func_args.get("seats", 1),
                                "fare": t["total_fare"],
                                "travel_date": func_args["travel_date"]
                            }
                    
                    tool_result_str = json.dumps(result)
                except Exception as e:
                    tool_result_str = json.dumps({"error": str(e)})
            else:
                tool_result_str = json.dumps({"error": f"Unknown tool: {func_name}"})
            
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result_str
            })
            
            # Post-tool state check: if LLM chose a train via check_seat_availability
            if func_name == "check_seat_availability" and session["state"] == BookingState.AWAITING_TRAIN_SELECTION:
                # Find the train in search_results to populate pending_booking
                res = json.loads(tool_result_str)
                if not res.get("error"):
                    session["pending_booking"] = {
                        "train_id": func_args["train_id"],
                        "train_name": res["train_name"],
                        "seats": func_args["seats_requested"],
                        "fare": res["total_fare"],
                        "travel_date": session.get("pending_search", {}).get("travel_date", date.today().strftime("%Y-%m-%d"))
                    }

    return "I'm having trouble processing your request. Please try again."
