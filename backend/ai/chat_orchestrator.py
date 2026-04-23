import re
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import Booking, ChatHistory
from services.booking_service import create_booking, get_user_bookings, serialize_booking
from services.payment_service import create_razorpay_order
from services.train_service import TrainSearchError, find_best_train_match, search_trains as search_trains_from_api
from services.station_matching import fuzzy_normalize_input, map_to_official_city


class BookingState(str, Enum):
    IDLE = "IDLE"
    AWAITING_SEARCH_DETAILS = "AWAITING_SEARCH_DETAILS"
    AWAITING_TRAIN_SELECTION = "AWAITING_TRAIN_SELECTION"
    AWAITING_SEAT_PREFERENCE = "AWAITING_SEAT_PREFERENCE"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    AWAITING_CONFLICT_RESOLUTION = "AWAITING_CONFLICT_RESOLUTION"
    PAID = "PAID"


class Intent(str, Enum):
    SEARCH_TRAINS = "SEARCH_TRAINS"
    BOOK_TICKET = "BOOK_TICKET"
    CHANGE_TRAIN = "CHANGE_TRAIN"
    CONFIRM_BOOKING = "CONFIRM_BOOKING"
    MAKE_PAYMENT = "MAKE_PAYMENT"
    HISTORY = "HISTORY"
    CANCEL = "CANCEL"
    NEW_QUERY = "NEW_QUERY"
    AFFIRMATIVE = "AFFIRMATIVE"
    NEGATIVE = "NEGATIVE"


SESSIONS: dict[int, dict[str, Any]] = {}


class ChatOrchestrator:
    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id

    def _save_chat(self, role: str, message: str, is_tool_message: bool = False) -> None:
        self.db.add(ChatHistory(user_id=self.user_id, role=role, message=message, is_tool_message=is_tool_message))
        self.db.commit()

    def _session(self) -> dict[str, Any]:
        if self.user_id not in SESSIONS:
            SESSIONS[self.user_id] = {
                "state": BookingState.IDLE,
                "search_results": [],
                "pending_search": None,
                "pending_booking": None,
                "confirmed_booking_id": None,
                "confirmed_total_fare": None,
                "pending_conflict": None,
            }
        return SESSIONS[self.user_id]

    @staticmethod
    def _empty_search() -> dict[str, Any]:
        return {
            "source": None,
            "destination": None,
            "travel_date": None,
            "seats": None,
            "seats_explicit": False,
        }

    def _pending_search(self, session: dict[str, Any]) -> dict[str, Any]:
        pending = session.get("pending_search")
        if not pending:
            pending = self._empty_search()
            session["pending_search"] = pending
        else:
            for key, value in self._empty_search().items():
                pending.setdefault(key, value)
        return pending

    def _clear_search_context(self, session: dict[str, Any], *, keep_pending_search: bool = False) -> None:
        session["search_results"] = []
        session["pending_booking"] = None
        if not keep_pending_search:
            session["pending_search"] = None

    def _reset_session(self, session: dict[str, Any]) -> None:
        session["state"] = BookingState.IDLE
        self._clear_search_context(session)
        session["confirmed_booking_id"] = None
        session["confirmed_total_fare"] = None

    def _assistant_response(self, session: dict[str, Any], response: str, **payload: Any) -> dict[str, Any]:
        self._save_chat("assistant", response)
        result = {
            "reply": response,
            "tool_calls": [],
            "booking_id": payload.get("booking_id"),
            "booking": payload.get("booking"),
            "payment_status": payload.get("payment_status"),
            "ticket_url": payload.get("ticket_url"),
            "razorpay_order": payload.get("razorpay_order"),
            "timestamp": datetime.utcnow().isoformat(),
        }
        return result

    @staticmethod
    def _normalize_input(message: str) -> str:
        # Step 1: Fuzzy correction (seta -> seat, etc.)
        normalized = fuzzy_normalize_input(message)
        
        # Step 2: Remove filler words (but keep those that might be part of station names unless they are leading/trailing)
        fillers = ["book", "ticket", "train", "available", "show", "please", "find", "for", "from", "to"]
        for filler in fillers:
            normalized = re.sub(rf"\b{filler}\b", "", normalized, flags=re.IGNORECASE)
            
        return normalized.strip()

    @staticmethod
    def _format_currency(amount: float) -> str:
        return f"Rs.{amount:,.2f}"

    @staticmethod
    def _clean_route_part(value: str) -> str:
        cleaned = value.strip(" ,.-")
        # Rule: Entities MUST NOT contain these words
        blacklist = [
            "book", "ticket", "tickets", "available", "avilable", "avlbl", "avail", "avalaible",
            "show", "train", "trains", "trian", "trai", "for", "from", "to", "please", 
            "me", "find", "search", "the", "a", "an", "is", "any", "some", "details", "of"
        ]
        
        # Remove common command prefixes (one or more)
        prefix_pattern = r"^(?:(?:" + "|".join(blacklist) + r")\b\s*)+"
        cleaned = re.sub(prefix_pattern, "", cleaned, flags=re.IGNORECASE)
        
        cleaned = re.sub(r"^\d+\s*(?:seat|seats|ticket|tickets)\b\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^(?:from|to|train|trains)\b\s*", "", cleaned, flags=re.IGNORECASE)
        
        # Double check: if the remaining word is in blacklist, it's invalid
        lowered = cleaned.lower()
        if lowered in blacklist or not lowered:
            return ""
        
        # City Normalization (official mapping)
        return map_to_official_city(cleaned)

    @staticmethod
    def _is_affirmative(message: str) -> bool:
        return bool(re.search(r"^\s*(yes|y|ok|okay|sure|confirm|proceed|pay|pay now|go ahead)\b", message, re.IGNORECASE))

    @staticmethod
    def _is_negative(message: str) -> bool:
        return bool(re.search(r"^\s*(no|n|cancel|stop|not now|later|back|nevermind)\b", message, re.IGNORECASE))

    @staticmethod
    def _extract_explicit_seat_count(message: str) -> Optional[int]:
        # Normalization already happened (seta -> seat), but we search specifically for seat patterns
        lowered = message.lower()
        
        # Pattern 1: NUMBER seat
        match1 = re.search(r"(\d+)\s*seat\b", lowered)
        if match1:
            return int(match1.group(1))
            
        # Pattern 2: seat NUMBER
        match2 = re.search(r"seat\s*(\d+)\b", lowered)
        if match2:
            return int(match2.group(1))
            
        # Pattern 3: Number near seat (within 10 chars)
        match3 = re.search(r"(\d+).{0,10}seat|seat.{0,10}(\d+)", lowered)
        if match3:
            return int(match3.group(1) or match3.group(2))

        return None

    @staticmethod
    def _extract_seat_preference(message: str) -> Optional[str]:
        lowered = message.lower()
        if "side lower" in lowered:
            return "Side Lower"
        if "side upper" in lowered:
            return "Side Upper"
        if "upper" in lowered:
            return "Upper"
        if "lower" in lowered:
            return "Lower"
        if "middle" in lowered:
            return "Middle"
        if "window" in lowered:
            return "Window"
        if "aisle" in lowered:
            return "Aisle"
        if "no preference" in lowered or "any seat" in lowered or "any berth" in lowered or "none" in lowered:
            return "No Preference"
        return None

    def _classify_intent(self, message: str, session: dict[str, Any]) -> Intent:
        lowered = message.lower()
        
        # 1. CHANGE_TRAIN: change + train, or just train number/name if already SELECTED
        if "change" in lowered and "train" in lowered:
            return Intent.CHANGE_TRAIN
        if session["state"] in [BookingState.AWAITING_TRAIN_SELECTION, BookingState.AWAITING_CONFIRMATION]:
             # If message looks like a train number or name
             if re.search(r"\b\d{5}\b", message) or any(kw in lowered for kw in ["express", "shatabdi", "rajdhani"]):
                  return Intent.CHANGE_TRAIN

        # 2. SEARCH_TRAINS: show/search/available + route (ensure not change)
        if any(kw in lowered for kw in ["show", "search", "available", "train", "trains"]) and "book" not in lowered:
             return Intent.SEARCH_TRAINS
             
        # 3. BOOK_TICKET: book + ticket/tickets
        if "book" in lowered:
             return Intent.BOOK_TICKET

        # 4. CONFIRM_BOOKING: yes/confirm/proceed while AWAITING_CONFIRMATION
        if self._is_affirmative(message) and session["state"] == BookingState.AWAITING_CONFIRMATION:
             return Intent.CONFIRM_BOOKING

        # 5. MAKE_PAYMENT: yes/pay/proceed while AWAITING_PAYMENT
        if self._is_affirmative(message) and session["state"] == BookingState.AWAITING_PAYMENT:
             return Intent.MAKE_PAYMENT

        # 6. HISTORY/CANCEL
        if any(kw in lowered for kw in ["history", "my booking", "my ticket"]):
            return Intent.HISTORY
        if "cancel" in lowered:
            return Intent.CANCEL

        # 7. Generic Affirmative/Negative
        if self._is_affirmative(message):
            return Intent.AFFIRMATIVE
        if self._is_negative(message):
            return Intent.NEGATIVE

        # Default: SEARCH if it has a route, otherwise NEW_QUERY
        if self._extract_route(message) or self._extract_partial_route(message)[0]:
             return Intent.SEARCH_TRAINS
             
        return Intent.NEW_QUERY

    @staticmethod
    def _has_explicit_reference(message: str) -> bool:
        """Checks if the user explicitly refers to the previous context."""
        lowered = message.lower()
        keywords = [
            "same route", "this route", "that route", "previous route",
            "same train", "this train", "that train", "previous train",
            "as before", "as above", "as mentioned", "same station"
        ]
        return any(kw in lowered for kw in keywords)

    def _detect_context_conflict(self, session: dict[str, Any], new_source: Optional[str], new_dest: Optional[str]) -> Optional[str]:
        """Detects if partial new details conflict with existing session details."""
        pending = session.get("pending_search") or {}
        old_source = pending.get("source")
        old_dest = pending.get("destination")
        
        if not old_source or not old_dest:
            return None
            
        if new_source and new_source.lower() != old_source.lower() and not new_dest:
            return f"Do you want to continue with {new_source} to {old_dest} or stay with {old_source} to {old_dest}?"
        
        if new_dest and new_dest.lower() != old_dest.lower() and not new_source:
            return f"Do you want to continue from {old_source} to {new_dest} or stay with {old_source} to {old_dest}?"
                
        return None

    @staticmethod
    def _extract_explicit_travel_date(message: str) -> Optional[date]:
        lowered = message.lower()
        today = date.today()

        if "day after tomorrow" in lowered:
            return today + timedelta(days=2)
        if "tomorrow" in lowered:
            return today + timedelta(days=1)
        if "today" in lowered:
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
        for day_name, weekday in weekday_map.items():
            if day_name in lowered:
                days_ahead = (weekday - today.weekday()) % 7
                if days_ahead <= 0:
                    days_ahead += 7
                return today + timedelta(days=days_ahead)

        iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", lowered)
        if iso_match:
            try:
                return date.fromisoformat(iso_match.group(1))
            except ValueError:
                pass

        slash_match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", lowered)
        if slash_match:
            day, month, year = map(int, slash_match.groups())
            try:
                return date(year, month, day)
            except ValueError:
                pass

        slash_no_year_match = re.search(r"\b(\d{1,2})[/-](\d{1,2})\b", lowered)
        if slash_no_year_match:
            day, month = map(int, slash_no_year_match.groups())
            try:
                candidate = date(today.year, month, day)
                if candidate < today:
                    candidate = date(today.year + 1, month, day)
                return candidate
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
        long_match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)(?:\s+(\d{4}))?\b", lowered)
        if long_match:
            day = int(long_match.group(1))
            month = month_names.get(long_match.group(2))
            year = int(long_match.group(3)) if long_match.group(3) else today.year
            if month:
                try:
                    candidate = date(year, month, day)
                    if not long_match.group(3) and candidate < today:
                        candidate = date(year + 1, month, day)
                    return candidate
                except ValueError:
                    pass

        return None

    def _extract_route(self, message: str) -> Optional[tuple[str, str]]:
        patterns = [
            (
                r"from\s+([a-z][a-z\s]{1,40}?)\s+to\s+([a-z][a-z\s]{1,40}?)"
                r"(?=\s+(?:\d+|seat|on|for|tomorrow|today|next|this|with|upper|lower|middle|"
                r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|[?.!,]|$)"
            ),
            (
                r"([a-z][a-z\s]{1,40}?)\s+to\s+([a-z][a-z\s]{1,40}?)"
                r"(?=\s+(?:\d+|seat|on|for|tomorrow|today|next|this|with|upper|lower|middle|"
                r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|[?.!,]|$)"
            ),
        ]

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if not match:
                continue

            source = self._clean_route_part(match.group(1))
            destination = self._clean_route_part(match.group(2))
            if source and destination and source.lower() != destination.lower():
                return source.title(), destination.title()
        return None

    def _extract_partial_route(self, message: str) -> tuple[Optional[str], Optional[str]]:
        patterns = {
            "source": (
                r"from\s+([a-z][a-z\s]{1,40}?)"
                r"(?=\s+(?:to|on|for|tomorrow|today|next|this|with|\d+|seat|"
                r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|[?.!,]|$)"
            ),
            "destination": (
                r"to\s+([a-z][a-z\s]{1,40}?)"
                r"(?=\s+(?:on|for|tomorrow|today|next|this|with|\d+|seat|"
                r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|[?.!,]|$)"
            ),
        }

        source = None
        destination = None

        source_match = re.search(patterns["source"], message, re.IGNORECASE)
        if source_match:
            source = self._clean_route_part(source_match.group(1)).title()

        destination_match = re.search(patterns["destination"], message, re.IGNORECASE)
        if destination_match:
            destination = self._clean_route_part(destination_match.group(1)).title()

        return source, destination

    def _guess_station_name(self, message: str) -> Optional[str]:
        cleaned = self._clean_route_part(message)
        lowered = cleaned.lower()
        if not cleaned:
            return None
        if re.search(
            r"\b(yes|no|pay|booking|ticket|tickets|seat|seats|tomorrow|today|history|cancel|help|start)\b",
            lowered,
        ):
            return None
        if not re.fullmatch(r"[a-z\s]+", lowered):
            return None
        if len(lowered.split()) > 3:
            return None
        return cleaned.title()

    def _update_pending_search_from_message(self, message: str, pending_search: dict[str, Any]) -> bool:
        # Rule 1 & 2: Latest message is source of truth. Reuse only if explicit.
        has_ref = self._has_explicit_reference(message)
        
        route = self._extract_route(message)
        new_source, new_dest = route if route else self._extract_partial_route(message)
        new_date = self._extract_explicit_travel_date(message)
        new_seats = self._extract_explicit_seat_count(message)
        
        # Rule 3: Each new query must override all previous journey details.
        if (new_source or new_dest) and not has_ref:
            if new_source and new_dest:
                pending_search["source"] = new_source
                pending_search["destination"] = new_dest
                pending_search["travel_date"] = new_date.isoformat() if new_date else None
                pending_search["seats"] = new_seats
                pending_search["seats_explicit"] = new_seats is not None
                return True
            
            if new_source: pending_search["source"] = new_source
            if new_dest: pending_search["destination"] = new_dest
            if new_date: pending_search["travel_date"] = new_date.isoformat()
            if new_seats is not None: 
                pending_search["seats"] = new_seats
                pending_search["seats_explicit"] = True
            return True

        updated = False
        if new_source and pending_search.get("source") != new_source:
            pending_search["source"] = new_source
            updated = True
        if new_dest and pending_search.get("destination") != new_dest:
            pending_search["destination"] = new_dest
            updated = True
        if new_date:
            iso_value = new_date.isoformat()
            if pending_search.get("travel_date") != iso_value:
                pending_search["travel_date"] = iso_value
                updated = True
        
        if new_seats is None:
            exact_number = re.fullmatch(r"\s*(\d+)\s*", message)
            if exact_number and not route and not new_date:
                new_seats = int(exact_number.group(1))

        if new_seats is not None and pending_search.get("seats") != new_seats:
            pending_search["seats"] = new_seats
            pending_search["seats_explicit"] = True
            updated = True
            
        return updated

    @staticmethod
    def _missing_search_fields(pending_search: dict[str, Any]) -> list[str]:
        missing = []
        for field in ("source", "destination", "travel_date"):
            if not pending_search.get(field):
                missing.append(field)
        return missing

    def _build_missing_search_prompt(self, pending_search: dict[str, Any]) -> str:
        known_bits = []
        if pending_search.get("source"):
            known_bits.append(f"source as {pending_search['source']}")
        if pending_search.get("destination"):
            known_bits.append(f"destination as {pending_search['destination']}")
        if pending_search.get("travel_date"):
            known_bits.append(f"date as {pending_search['travel_date']}")
        if pending_search.get("seats_explicit") and pending_search.get("seats"):
            known_bits.append(f"{pending_search['seats']} seat(s)")

        prompts = []
        if not pending_search.get("source") and not pending_search.get("destination"):
            prompts.append("Please tell me the source and destination.")
        elif not pending_search.get("source"):
            prompts.append("What is the source station?")
        elif not pending_search.get("destination"):
            prompts.append("What destination would you like to travel to?")

        if not pending_search.get("travel_date"):
            prompts.append("What date would you like to travel?")

        prefix = ""
        if known_bits:
            prefix = "I have " + ", ".join(known_bits) + ". "

        return (
            prefix
            + " ".join(prompts)
            + " You can also tell me seats now, otherwise I will assume 1 seat for search."
        )

    def _format_search_results(self, results: list[dict[str, Any]], seats: int, seats_explicit: bool, travel_date: str) -> str:
        header_source = results[0]["source"] if results else "your source"
        header_destination = results[0]["destination"] if results else "your destination"
        lines = [f"Found {len(results)} train(s) from {header_source} to {header_destination} on {travel_date}:"]
        for index, train in enumerate(results[:5], start=1):
            train_ref = train.get("train_number") or train.get("train_id") or train.get("id")
            fare_label = (
                f"Fare for {seats}: {self._format_currency(train['total_fare'])}"
                if seats_explicit
                else f"Fare per seat: {self._format_currency(train['fare_per_seat'])}"
            )
            lines.append(
                f"{index}. {train['train_name']} ({train_ref}) | "
                f"{train['departure_time']} -> {train['arrival_time']} | "
                f"Seats left: {train['seats_available']} | "
                f"{fare_label}"
            )
        lines.append("Reply with the list number or train number to continue.")
        return "\n".join(lines)

    def _build_booking_summary(self, booking: dict[str, Any]) -> str:
        train_ref = booking.get("train_number") or booking.get("train_id") or "N/A"
        return (
            "### JOURNEY DETAILS ###\n"
            f"Source: {booking['source']}\n"
            f"Destination: {booking['destination']}\n"
            f"Train: {booking['train_name']} ({train_ref})\n"
            f"Date: {booking['travel_date']}\n"
            "------------------------\n"
            f"Departure: {booking['departure_time']} | Arrival: {booking['arrival_time']}\n"
            f"Seats: {booking['seats']}\n"
            f"Seat preference: {booking['seat_preference']}\n"
            f"Total Fare: {self._format_currency(booking['total_fare'])}\n\n"
            "Reply YES to confirm booking, or tell me what you want to change."
        )

    def _build_seat_preference_prompt(self, booking: dict[str, Any]) -> str:
        return (
            f"You selected {booking['train_name']} for {booking['travel_date']}.\n"
            f"What seat preference would you like for {booking['seats']} seat(s)? "
            "Reply with Lower, Upper, Middle, Side Lower, Side Upper, or No Preference."
        )

    def _select_train_from_message(self, message: str, results: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if not results:
            return None

        list_choice = re.search(r"(?:train|option|number)\s*(\d+)\b", message, re.IGNORECASE)
        if list_choice:
            choice = int(list_choice.group(1))
            if 1 <= choice <= len(results):
                return results[choice - 1]

        exact_number = re.fullmatch(r"\s*(\d+)\s*", message)
        if exact_number:
            choice = int(exact_number.group(1))
            if 1 <= choice <= len(results):
                return results[choice - 1]

        digit_match = re.search(r"\b(\d{3,6})\b", message)
        if digit_match:
            choice = digit_match.group(1)
            for result in results:
                if choice in {
                    str(result.get("train_number") or ""),
                    str(result.get("train_id") or ""),
                    str(result.get("id") or ""),
                }:
                    return result

        return find_best_train_match(message, results, minimum_score=0.72)

    def _latest_pending_booking(self) -> Optional[Booking]:
        return (
            self.db.query(Booking)
            .filter(Booking.user_id == self.user_id, Booking.status == "PENDING")
            .order_by(Booking.created_at.desc())
            .first()
        )

    def _latest_pending_booking_payload(self) -> Optional[dict[str, Any]]:
        booking = self._latest_pending_booking()
        if not booking:
            return None
        return {
            "booking_id": booking.id,
            "total_fare": float(booking.total_fare),
        }

    def _should_handle_search_input(self, message: str, session: dict[str, Any]) -> bool:
        if self._is_affirmative(message) or self._is_negative(message):
            return False
        if self._extract_route(message):
            return True
        if self._extract_explicit_travel_date(message):
            return True
        if self._extract_partial_route(message) != (None, None):
            return True
        if session["state"] == BookingState.AWAITING_SEARCH_DETAILS:
            return True
        return False

    def _selected_train_from_booking(self, pending_booking: dict[str, Any]) -> dict[str, Any]:
        return {
            "train_id": pending_booking.get("train_id"),
            "train_number": pending_booking.get("train_number"),
            "train_name": pending_booking.get("train_name"),
            "source": pending_booking.get("source"),
            "destination": pending_booking.get("destination"),
            "travel_date": pending_booking.get("travel_date"),
            "departure_time": pending_booking.get("departure_time"),
            "arrival_time": pending_booking.get("arrival_time"),
            "fare_per_seat": pending_booking.get("fare_per_seat"),
            "seats_available": pending_booking.get("seats_available"),
            "data_source": pending_booking.get("data_source"),
        }

    def _booking_from_selected_train(self, selected_train: dict[str, Any], pending_search: dict[str, Any]) -> dict[str, Any]:
        seats = pending_search.get("seats") or 1
        return {
            "train_id": selected_train.get("train_id"),
            "train_number": selected_train.get("train_number"),
            "train_name": selected_train["train_name"],
            "source": selected_train["source"],
            "destination": selected_train["destination"],
            "travel_date": selected_train["travel_date"],
            "departure_time": selected_train["departure_time"],
            "arrival_time": selected_train["arrival_time"],
            "seats": seats,
            "seat_preference": "No Preference",
            "fare_per_seat": float(selected_train["fare_per_seat"]),
            "total_fare": round(float(selected_train["fare_per_seat"]) * seats, 2),
            "seats_available": int(selected_train.get("seats_available") or 0),
            "data_source": selected_train.get("data_source", "api"),
        }

    def _update_pending_booking(self, session: dict[str, Any], message: str) -> tuple[bool, Optional[str]]:
        pending_booking = session.get("pending_booking")
        if not pending_booking:
            return False, None

        changed = False
        seat_count = self._extract_explicit_seat_count(message)
        if seat_count is not None:
            seats_left = int(pending_booking.get("seats_available") or 0)
            if seats_left and seat_count > seats_left:
                return False, f"Only {seats_left} seat(s) are available on this train. Please choose a smaller number."

            pending_booking["seats"] = seat_count
            pending_booking["total_fare"] = round(float(pending_booking["fare_per_seat"]) * seat_count, 2)
            pending_search = self._pending_search(session)
            pending_search["seats"] = seat_count
            pending_search["seats_explicit"] = True
            changed = True

        preference = self._extract_seat_preference(message)
        if preference and pending_booking.get("seat_preference") != preference:
            pending_booking["seat_preference"] = preference
            changed = True

        return changed, None

    def _handle_search_input(self, message: str, session: dict[str, Any]) -> dict[str, Any]:
        # Fail-Safe Conflict Detection
        if not self._has_explicit_reference(message):
            route = self._extract_route(message)
            new_source, new_dest = route if route else self._extract_partial_route(message)
            conflict_msg = self._detect_context_conflict(session, new_source, new_dest)
            if conflict_msg:
                session["state"] = BookingState.AWAITING_CONFLICT_RESOLUTION
                session["pending_conflict"] = {"source": new_source, "destination": new_dest}
                return self._assistant_response(session, conflict_msg)

        pending_search = self._pending_search(session)
        self._update_pending_search_from_message(message, pending_search)
        self._clear_search_context(session, keep_pending_search=True)

        missing = self._missing_search_fields(pending_search)
        if missing:
            session["state"] = BookingState.AWAITING_SEARCH_DETAILS
            return self._assistant_response(session, self._build_missing_search_prompt(pending_search))

        seats = pending_search.get("seats") or 1
        try:
            results = search_trains_from_api(
                pending_search["source"],
                pending_search["destination"],
                pending_search["travel_date"],
                seats=seats,
            )
        except TrainSearchError as exc:
            session["state"] = BookingState.AWAITING_SEARCH_DETAILS
            return self._assistant_response(
                session,
                f"I could not fetch trains right now: {exc} Please check the RapidAPI configuration and try again.",
            )

        session["search_results"] = results
        if not results:
            session["state"] = BookingState.AWAITING_SEARCH_DETAILS
            return self._assistant_response(
                session,
                (
                    f"No trains found from {pending_search['source']} to {pending_search['destination']} "
                    f"on {pending_search['travel_date']}.\n"
                    "Tell me another date, change the route, or choose a different train query."
                ),
            )

        session["state"] = BookingState.AWAITING_TRAIN_SELECTION
        return self._assistant_response(
            session,
            self._format_search_results(
                results,
                seats,
                bool(pending_search.get("seats_explicit")),
                pending_search["travel_date"],
            ),
        )

    def _handle_payment_state(self, message: str, session: dict[str, Any]) -> dict[str, Any]:
        if self._is_affirmative(message):
            pending = self._latest_pending_booking_payload()
            booking_id = session.get("confirmed_booking_id") or (pending or {}).get("booking_id")
            if not booking_id:
                self._reset_session(session)
                return self._assistant_response(
                    session,
                    "I could not find a pending booking to pay for. Please search for a train again.",
                )

            try:
                order_data = create_razorpay_order(self.db, booking_id, self.user_id)
            except HTTPException as exc:
                return self._assistant_response(
                    session,
                    str(exc.detail) if isinstance(exc.detail, str) else "I could not initialize payment right now.",
                )
            except Exception:
                return self._assistant_response(
                    session,
                    "I could not initialize Razorpay payment right now. Please try again in a moment.",
                )

            return self._assistant_response(
                session,
                f"Opening secure payment gateway for Booking #{booking_id}. Please complete the payment in the popup.",
                booking_id=booking_id,
                razorpay_order=order_data,
            )

        if self._is_negative(message):
            session["state"] = BookingState.IDLE
            return self._assistant_response(
                session,
                "Okay. Your booking is still pending, so you can type YES later to open payment.",
                booking_id=session.get("confirmed_booking_id"),
            )

        return self._assistant_response(
            session,
            "Reply YES to open Razorpay payment, or NO if you want to pay later.",
            booking_id=session.get("confirmed_booking_id"),
        )

    def _handle_confirmation_state(self, message: str, session: dict[str, Any]) -> dict[str, Any]:
        changed, error_message = self._update_pending_booking(session, message)
        if error_message:
            return self._assistant_response(session, error_message)
        if changed:
            return self._assistant_response(session, self._build_booking_summary(session["pending_booking"]))

        if self._should_handle_search_input(message, session):
            return self._handle_search_input(message, session)

        if self._is_affirmative(message):
            pending_booking = session.get("pending_booking")
            if not pending_booking:
                self._reset_session(session)
                return self._assistant_response(
                    session,
                    "I lost the booking details for that request. Please search for a train again.",
                )

            try:
                booking = create_booking(
                    self.db,
                    self.user_id,
                    self._selected_train_from_booking(pending_booking),
                    pending_booking["seats"],
                    pending_booking["seat_preference"],
                    date.fromisoformat(pending_booking["travel_date"]),
                )
            except HTTPException as exc:
                self._reset_session(session)
                return self._assistant_response(
                    session,
                    str(exc.detail) if isinstance(exc.detail, str) else "Booking failed. Please search again.",
                )

            session["state"] = BookingState.AWAITING_PAYMENT
            session["confirmed_booking_id"] = booking.id
            session["confirmed_total_fare"] = float(booking.total_fare)
            response = (
                "Booking created successfully.\n"
                f"Booking ID: #{booking.id}\n"
                f"Seats: {booking.seat_numbers}\n"
                f"Total Fare: {self._format_currency(float(booking.total_fare))}\n"
                "Reply YES to open Razorpay payment or NO to pay later."
            )
            return self._assistant_response(session, response, booking_id=booking.id)

        if self._is_negative(message):
            self._reset_session(session)
            return self._assistant_response(session, "Booking cancelled. You can search for another train anytime.")

        return self._assistant_response(
            session,
            "Reply YES to confirm the booking, or tell me what you want to change.",
        )

    def _handle_seat_preference_state(self, message: str, session: dict[str, Any]) -> dict[str, Any]:
        if self._is_negative(message):
            self._reset_session(session)
            return self._assistant_response(session, "Booking cancelled. You can search for another train anytime.")

        changed, error_message = self._update_pending_booking(session, message)
        if error_message:
            return self._assistant_response(session, error_message)

        preference = self._extract_seat_preference(message)
        pending_booking = session.get("pending_booking")
        if not pending_booking:
            self._reset_session(session)
            return self._assistant_response(session, "I lost the selected train details. Please search again.")

        if preference:
            pending_booking["seat_preference"] = preference
            session["state"] = BookingState.AWAITING_CONFIRMATION
            return self._assistant_response(session, self._build_booking_summary(pending_booking))

        if changed:
            return self._assistant_response(session, self._build_seat_preference_prompt(pending_booking))

        if self._should_handle_search_input(message, session):
            return self._handle_search_input(message, session)

        return self._assistant_response(
            session,
            "Please reply with Lower, Upper, Middle, Side Lower, Side Upper, or No Preference.",
        )

    def _handle_train_selection_state(self, message: str, session: dict[str, Any]) -> dict[str, Any]:
        selected_train = self._select_train_from_message(message, session.get("search_results", []))
        if selected_train:
            pending_search = self._pending_search(session)
            pending_booking = self._booking_from_selected_train(selected_train, pending_search)
            session["pending_booking"] = pending_booking

            preference = self._extract_seat_preference(message)
            if preference:
                pending_booking["seat_preference"] = preference
                session["state"] = BookingState.AWAITING_CONFIRMATION
                return self._assistant_response(session, self._build_booking_summary(pending_booking))

            session["state"] = BookingState.AWAITING_SEAT_PREFERENCE
            return self._assistant_response(session, self._build_seat_preference_prompt(pending_booking))

        if self._should_handle_search_input(message, session):
            return self._handle_search_input(message, session)

        if self._is_negative(message):
            self._reset_session(session)
            return self._assistant_response(session, "Search cancelled. Tell me a new route whenever you're ready.")

        return self._assistant_response(
            session,
            "I couldn't match that train selection. Reply with the list number or train number, or tell me another date or route.",
        )

    def _handle_history(self, session: dict[str, Any]) -> dict[str, Any]:
        history = get_user_bookings(self.db, self.user_id)
        if not history:
            return self._assistant_response(session, "You don't have any bookings yet. Start with a route and date.")

        lines = ["Here are your recent bookings:"]
        for item in history[:5]:
            lines.append(
                f"- #{item['id']} | {item['train_name']} | {item['source']} -> {item['destination']} | "
                f"{item['booking_date']} | {self._format_currency(float(item['total_fare']))} | {item['status']}"
            )
        return self._assistant_response(session, "\n".join(lines))

    def _handle_cancel_request(self, booking_id: int, session: dict[str, Any]) -> dict[str, Any]:
        booking = (
            self.db.query(Booking)
            .filter(Booking.id == booking_id, Booking.user_id == self.user_id)
            .first()
        )
        if not booking:
            return self._assistant_response(session, "Cancellation failed: Booking not found.")

        if booking.status == "CANCELLED":
            return self._assistant_response(session, "This booking is already cancelled.")

        if booking.status == "CONFIRMED" and booking.booking_date <= date.today():
            return self._assistant_response(session, "Same-day or past confirmed bookings cannot be cancelled.")

        booking.status = "CANCELLED"
        self.db.add(booking)
        self.db.commit()
        self._reset_session(session)
        return self._assistant_response(session, f"Booking #{booking_id} cancelled successfully.")

    def _handle_conflict_resolution(self, message: str, session: dict[str, Any]) -> dict[str, Any]:
        conflict = session.get("pending_conflict")
        if not conflict:
            session["state"] = BookingState.IDLE
            return self._handle_search_input(message, session)
            
        if self._is_affirmative(message):
            # User wants the new route
            pending_search = self._pending_search(session)
            if conflict.get("source"): pending_search["source"] = conflict["source"]
            if conflict.get("destination"): pending_search["destination"] = conflict["destination"]
            session["state"] = BookingState.IDLE 
            session["pending_conflict"] = None
            return self._handle_search_input(message, session)
            
        if self._is_negative(message):
            # User wants to stay with previous route
            session["state"] = BookingState.IDLE
            session["pending_conflict"] = None
            return self._assistant_response(session, "Okay, continuing with your previous route. What would you like to do next?")
            
        return self._assistant_response(session, "Please reply with YES to use the new route or NO to keep the previous one.")

    @classmethod
    def clear_session(cls, user_id: int) -> None:
        if user_id in SESSIONS:
            del SESSIONS[user_id]

    def handle_message(self, user_message: str) -> dict[str, Any]:
        raw_message = (user_message or "").strip()
        if not raw_message:
            return {
                "reply": "I didn't receive any message. How can I help you?",
                "tool_calls": [],
                "timestamp": datetime.utcnow().isoformat(),
            }

        # Step 1: Input Normalization (lowercase + fuzzy corrections like seta -> seat)
        message = fuzzy_normalize_input(raw_message)
        
        session = self._session()
        self._save_chat("user", message)
        
        # 1. Classify Intent
        intent = self._classify_intent(message, session)
        
        # 2. State Transition Rules
        
        # Rule: SEARCH_TRAINS ALWAYS RESET
        if intent == Intent.SEARCH_TRAINS:
            self._reset_session(session)
            return self._handle_search_input(message, session)

        # Rule: AFTER PAYMENT (IDLE but status was PAID) -> Handled by route reset,
        # but if we are here, we check if state is PAID
        if session["state"] == BookingState.PAID:
             self._reset_session(session)
             # Next message is treated as a new query
             return self.handle_message(message)

        # Rule: CHANGE_TRAIN must overwrite train_number
        if intent == Intent.CHANGE_TRAIN:
             # If we are in selection or confirmation, we update selection
             return self._handle_train_selection_state(message, session)

        # 3. Execution based on State + Intent
        
        if intent == Intent.HISTORY:
            return self._handle_history(session)
            
        if intent == Intent.CANCEL:
            cancel_match = re.search(r"cancel\s+(?:booking\s*)?#?(\d+)", message, re.IGNORECASE)
            if cancel_match:
                return self._handle_cancel_request(int(cancel_match.group(1)), session)
            return self._assistant_response(session, "Please provide the booking ID to cancel, e.g., 'cancel booking #123'.")

        # Contextual Handlers
        if session["state"] == BookingState.AWAITING_CONFLICT_RESOLUTION:
            return self._handle_conflict_resolution(message, session)

        if session["state"] == BookingState.AWAITING_PAYMENT:
            return self._handle_payment_state(message, session)

        if session["state"] == BookingState.AWAITING_CONFIRMATION:
            return self._handle_confirmation_state(message, session)

        if session["state"] == BookingState.AWAITING_SEAT_PREFERENCE:
            return self._handle_seat_preference_state(message, session)

        if session["state"] == BookingState.AWAITING_TRAIN_SELECTION:
            return self._handle_train_selection_state(message, session)

        if intent == Intent.BOOK_TICKET:
             # Try to process as search/book input
             return self._handle_search_input(message, session)

        # Default fallback
        if any(word in message.lower() for word in ["hi", "hello", "hey", "help", "start"]):
            return self._assistant_response(
                session,
                "please share source,destination,date,seat."
            )

        # If it looks like search details but not explicit intent
        if self._should_handle_search_input(message, session):
            return self._handle_search_input(message, session)

        return self._assistant_response(
            session,
            "please share source,destination,date,seat."
        )
