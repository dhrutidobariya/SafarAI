import json
import re
from datetime import date, datetime, timedelta
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from ai.mcp_tools import MCPToolRegistry, TOOL_DEFINITIONS
from config import settings
from models import Booking, ChatHistory


class ChatOrchestrator:
    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self.client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self.tools = MCPToolRegistry(db, user_id)

    def _save_chat(self, role: str, message: str, is_tool_message: bool = False):
        self.db.add(ChatHistory(user_id=self.user_id, role=role, message=message, is_tool_message=is_tool_message))
        self.db.commit()

    def _recent_context(self) -> str:
        rows = (
            self.db.query(ChatHistory)
            .filter(ChatHistory.user_id == self.user_id)
            .order_by(ChatHistory.created_at.desc())
            .limit(8)
            .all()
        )
        rows.reverse()
        return "\n".join([f"{r.role}: {r.message}" for r in rows])

    def _latest_requested_seats(self) -> int:
        rows = (
            self.db.query(ChatHistory)
            .filter(ChatHistory.user_id == self.user_id, ChatHistory.role == "user")
            .order_by(ChatHistory.created_at.desc())
            .limit(12)
            .all()
        )
        for row in rows:
            match = re.search(r"(\d+)\s*(?:ticket|seat)s?", row.message.lower())
            if match:
                return int(match.group(1))
        return 1

    def _latest_pending_booking(self):
        return (
            self.db.query(Booking)
            .filter(Booking.user_id == self.user_id, Booking.status == "PENDING")
            .order_by(Booking.created_at.desc())
            .first()
        )

    def _extract_travel_date(self, user_message: str) -> date:
        msg = user_message.lower()
        today = date.today()

        if "tomorrow" in msg:
            return today + timedelta(days=1)
        if "today" in msg:
            return today

        weekday_map = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        # Check weekdays
        for day_name, weekday in weekday_map.items():
            if day_name in msg:
                days_ahead = (weekday - today.weekday()) % 7
                if days_ahead <= 0:  # If today or already passed this week, move to next week
                    days_ahead += 7
                return today + timedelta(days=days_ahead)

        iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", msg)
        if iso_match:
            try:
                return date.fromisoformat(iso_match.group(1))
            except ValueError:
                pass

        slash_match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", msg)
        if slash_match:
            day, month, year = map(int, slash_match.groups())
            try:
                return date(year, month, day)
            except ValueError:
                pass

        month_names = {
            "january": 1,
            "february": 2,
            "march": 3,
            "april": 4,
            "may": 5,
            "june": 6,
            "july": 7,
            "august": 8,
            "september": 9,
            "october": 10,
            "november": 11,
            "december": 12,
        }
        # Long date pattern (e.g., 16 April 2026)
        for match in re.finditer(r"\b(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})\b", msg):
            day = int(match.group(1))
            month_name = match.group(2).lower()
            year = int(match.group(3))
            month = month_names.get(month_name)
            if month:
                try:
                    return date(year, month, day)
                except ValueError:
                    pass

        # Day Month pattern (e.g., 16 April)
        for match in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-zA-Z]+)\b", msg):
            day = int(match.group(1))
            month_name = match.group(2).lower()
            month = month_names.get(month_name)
            if month:
                try:
                    candidate = date(today.year, month, day)
                    if candidate < today:
                        candidate = date(today.year + 1, month, day)
                    return candidate
                except ValueError:
                    pass

        # If no date found in current message, check history only if no explicit date was likely intended
        history = self._recent_context().lower()
        if "tomorrow" in history:
            return today + timedelta(days=1)
        if "today" in history:
            return today
        
        iso_match_hist = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", history)
        if iso_match_hist:
            try:
                return date.fromisoformat(iso_match_hist.group(1))
            except ValueError:
                pass

        return today

    def _format_tool_based_reply(self, parsed: dict[str, Any], tool_results: list[dict[str, Any]]) -> str | None:
        if not tool_results:
            return None

        error_lines = []
        for item in tool_results:
            if item.get("error"):
                error_lines.append(f"- {item['name']}: {item['error']}")
        if error_lines:
            return "I hit an issue while processing your request:\n" + "\n".join(error_lines)

        lines: list[str] = []
        for item in tool_results:
            name = item.get("name")
            result = item.get("result")
            args = item.get("arguments", {})

            if name == "search_trains":
                source = args.get("source", "")
                destination = args.get("destination", "")
                travel_date = args.get("travel_date", "")
                if not result:
                    lines.append(
                        f"No trains found from {source} to {destination} on {travel_date}. "
                        "Try another date or route."
                    )
                else:
                    lines.append(f"Found {len(result)} train(s) from {source} to {destination} on {travel_date}:")
                    for train in result[:5]:
                        lines.append(
                            f"- Train {train['id']}: {train['train_name']} | "
                            f"{train['departure_time']} -> {train['arrival_time']} | "
                            f"Seats: {train['seats_available']} | Fare: {train['fare_per_seat']}"
                        )
                    lines.append("Reply with the train id like: Book train 3 for 2 tickets.")

            elif name == "check_availability" and isinstance(result, dict):
                if result.get("available"):
                    lines.append(
                        f"Seats are available. Seats left: {result.get('seats_left', 'N/A')}."
                    )
                else:
                    lines.append(result.get("message", "Seats are not available for this train."))

            elif name == "book_ticket" and isinstance(result, dict):
                lines.append(
                    f"Booking created successfully. Booking ID: {result.get('booking_id')}, "
                    f"Total fare: {result.get('total_fare')}."
                )
                lines.append("Reply 'yes' to proceed with payment.")

            elif name == "process_payment" and isinstance(result, dict):
                if result.get("status") == "SUCCESS":
                    lines.append(
                        f"Payment successful. Transaction ID: {result.get('transaction_id', 'N/A')}."
                    )
                else:
                    lines.append("Payment failed. Please try again.")

            elif name == "generate_ticket":
                lines.append("Your ticket is generated.")

        if not lines and parsed.get("final_reply"):
            return parsed["final_reply"]
        return "\n".join(lines) if lines else None

    def _rule_based_parse(self, user_message: str) -> dict[str, Any]:
        msg = user_message.lower()
        cities = re.findall(r"\b([a-zA-Z]+)\s+to\s+([a-zA-Z]+)\b", msg)
        seats = re.search(r"(\d+)\s*(?:ticket|seat)s?", msg)
        selected_train = re.search(r"train\s+(\d+)", msg)
        travel_date = self._extract_travel_date(user_message)
        if cities:
            # Filter matches to skip common false positive words
            best_city_pair = cities[0]
            for source, dest in cities:
                if source not in {"tickets", "travel", "book", "train"} and dest not in {"book", "find"}:
                    best_city_pair = (source, dest)
                    break
            return {
                "intent": "search_and_book",
                "tool_calls": [
                    {
                        "name": "search_trains",
                        "arguments": {
                            "source": best_city_pair[0].title(),
                            "destination": best_city_pair[1].title(),
                            "travel_date": travel_date.isoformat(),
                        },
                    }
                ],
                "context": {"seats": int(seats.group(1)) if seats else 1},
            }
        if selected_train:
            return {
                "intent": "ask_preference",
                "tool_calls": [],
                "final_reply": f"Train {selected_train.group(1)} selected. What is your seat preference? (e.g., Upper, Lower, or Middle berth)",
                "context": {"train_id": int(selected_train.group(1))}
            }

        # Check for seat preference response
        if any(pref in msg for pref in ["upper", "lower", "middle", "no preference", "any seat"]):
            preference = "No Preference"
            for p in ["upper", "lower", "middle"]:
                if p in msg:
                    preference = p.title()
            
            # Find the most recently selected train ID from history
            history = self._recent_context().lower()
            train_match = re.findall(r"train\s+(\d+)", history)
            if train_match:
                train_id = int(train_match[-1])
                seat_count = self._latest_requested_seats()
                return {
                    "intent": "train_selected",
                    "tool_calls": [
                        {"name": "check_availability", "arguments": {"train_id": train_id, "seats": seat_count}},
                        {
                            "name": "book_ticket",
                            "arguments": {
                                "user_id": self.user_id,
                                "train_id": train_id,
                                "seats": seat_count,
                                "preference": preference
                            },
                        },
                    ],
                    "final_reply": f"Seats are available. Booking created with {preference} preference. Proceed to payment?",
                }
        if any(word in msg for word in ["yes", "proceed", "pay", "go ahead", "confirm", "ok", "sure", "do it"]):
            pending = self._latest_pending_booking()
            if pending:
                return {
                    "intent": "payment",
                    "tool_calls": [
                        {"name": "process_payment", "arguments": {"booking_id": pending.id, "amount": pending.total_fare}},
                        {"name": "generate_ticket", "arguments": {"booking_id": pending.id}},
                    ],
                    "final_reply": "Payment successful. Ticket generated.",
                }
        return {"intent": "generic", "tool_calls": [], "context": {}}

    def _llm_parse(self, user_message: str) -> dict[str, Any]:
        if not self.client:
            return self._rule_based_parse(user_message)
        system = (
            "You are a railway booking assistant using MCP-style tools. "
            "Return strict JSON with keys: intent, tool_calls(list of {name,arguments}), final_reply. "
            f"Allowed tools: {json.dumps(TOOL_DEFINITIONS)}"
        )
        prompt = f"Recent conversation:\n{self._recent_context()}\n\nUser message: {user_message}"
        try:
            response = self.client.responses.create(
                model=settings.openai_model,
                input=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                temperature=0.2,
            )
            text = response.output_text.strip()
            return json.loads(text)
        except Exception:
            return self._rule_based_parse(user_message)

    def handle_message(self, user_message: str) -> dict[str, Any]:
        self._save_chat("user", user_message)
        parsed = self._llm_parse(user_message)
        tool_results = []
        booking_id = None
        payment_status = None
        ticket_url = None

        for tool_call in parsed.get("tool_calls", []):
            name = tool_call.get("name")
            args = tool_call.get("arguments", {})
            if name == "book_ticket":
                args["user_id"] = self.user_id
            try:
                result = self.tools.call(name, args)
                tool_results.append({"name": name, "arguments": args, "result": result})
                self._save_chat("tool", json.dumps({"name": name, "result": result}), is_tool_message=True)
                if name == "book_ticket":
                    booking_id = result.get("booking_id")
                if name == "process_payment":
                    payment_status = result.get("status")
                    if not booking_id:
                        booking_id = args.get("booking_id")
                if name == "generate_ticket":
                    ticket_booking_id = args.get("booking_id") or booking_id
                    if ticket_booking_id:
                        booking_id = ticket_booking_id
                        ticket_url = f"/ticket/{ticket_booking_id}"
            except Exception as exc:
                tool_results.append({"name": name, "arguments": args, "error": str(exc)})

        final_reply = parsed.get("final_reply")
        generated_reply = self._format_tool_based_reply(parsed, tool_results)
        if generated_reply:
            final_reply = generated_reply
        elif not final_reply:
            final_reply = (
                "Please share source, destination, date, and number of seats. "
                "Example: Book 2 tickets from Surat to Mumbai tomorrow."
            )
        if booking_id and payment_status == "SUCCESS":
            ticket_url = f"/ticket/{booking_id}"

        self._save_chat("assistant", final_reply)
        return {
            "reply": final_reply,
            "tool_calls": tool_results,
            "booking_id": booking_id,
            "payment_status": payment_status,
            "ticket_url": ticket_url,
            "timestamp": datetime.utcnow().isoformat(),
        }
