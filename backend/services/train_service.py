import os
import re
from datetime import date, datetime
from typing import Any, Iterable, Optional

import requests

from services.station_matching import normalize_station_name, station_match_score, text_match_score


RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "indian-railway-irctc.p.rapidapi.com")
RAPIDAPI_TRAIN_ENDPOINT = os.getenv(
    "RAPIDAPI_TRAIN_ENDPOINT",
    "https://indian-railway-irctc.p.rapidapi.com/api/trains-search",
)
RAPIDAPI_MOCK = str(os.getenv("RAPIDAPI_MOCK", "false")).lower() == "true"


class TrainSearchError(RuntimeError):
    pass


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value in (None, "", [], {}, ()):
            continue
        return value
    return None


def _safe_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, dict):
        return _safe_string(
            _coalesce(
                value.get("name"),
                value.get("station_name"),
                value.get("stationName"),
                value.get("code"),
                value.get("station_code"),
                value.get("stationCode"),
            )
        )
    if isinstance(value, list):
        for item in value:
            resolved = _safe_string(item)
            if resolved:
                return resolved
        return None

    text = str(value).strip()
    return text or None


def _extract_station_value(value: Any) -> tuple[Optional[str], Optional[str]]:
    if value is None:
        return None, None

    if isinstance(value, dict):
        name = _safe_string(
            _coalesce(
                value.get("name"),
                value.get("station_name"),
                value.get("stationName"),
                value.get("station"),
                value.get("city"),
            )
        )
        code = _safe_string(
            _coalesce(
                value.get("code"),
                value.get("station_code"),
                value.get("stationCode"),
                value.get("short_code"),
            )
        )
        return name, code.upper() if code else None

    if isinstance(value, list):
        resolved_name = None
        resolved_code = None
        for item in value:
            item_name, item_code = _extract_station_value(item)
            if not resolved_name and item_name:
                resolved_name = item_name
            if not resolved_code and item_code:
                resolved_code = item_code
            if resolved_name and resolved_code:
                break
        return resolved_name, resolved_code

    text = _safe_string(value)
    if not text:
        return None, None

    compact = text.strip()
    if compact.isalpha() and compact.upper() == compact and 2 <= len(compact) <= 5:
        return None, compact.upper()

    code_match = re.search(r"\(([A-Za-z]{2,5})\)", compact)
    code = code_match.group(1).upper() if code_match else None
    name = re.sub(r"\([A-Za-z]{2,5}\)", " ", compact)
    name = _safe_string(name)

    if name and code and normalize_station_name(name) == normalize_station_name(code):
        name = None

    return name, code


def _coalesce_station(*values: Any) -> tuple[Optional[str], Optional[str]]:
    resolved_name = None
    resolved_code = None

    for value in values:
        name, code = _extract_station_value(value)
        if not resolved_name and name:
            resolved_name = name
        if not resolved_code and code:
            resolved_code = code
        if resolved_name and resolved_code:
            break

    return resolved_name, resolved_code


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value)
    text = text.replace(",", "")
    text = text.replace("Rs.", "")
    text = text.replace("Rs", "")
    text = text.replace("INR", "")
    text = text.strip()

    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)

    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if not digits:
        return default
    try:
        return int(digits)
    except ValueError:
        return default


def _safe_date(value: Any, requested_date: str) -> str:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()

    text = _safe_string(value)
    if not text:
        return requested_date

    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue

    return requested_date


def _safe_time(value: Any) -> str:
    text = _safe_string(value)
    if not text:
        return "N/A"

    text = text.replace(".", ":")
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M%p"):
        try:
            return datetime.strptime(text, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return text


def _candidate_lists(payload: Any) -> Iterable[list[dict[str, Any]]]:
    if isinstance(payload, list):
        if all(isinstance(item, dict) for item in payload):
            yield payload
        return

    if not isinstance(payload, dict):
        return

    if payload.get("status") in {"error", "failed"}:
        return

    keys = (
        "data",
        "trains",
        "results",
        "result",
        "body",
        "response",
        "payload",
        "items",
        "available_trains",
        "availableTrains",
        "train_list",
    )
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            yield value
        elif isinstance(value, dict):
            yield from _candidate_lists(value)

    if any(key in payload for key in ("train_name", "train_number", "number", "id")):
        yield [payload]


def _normalize_train(item: dict[str, Any], source: str, destination: str, travel_date: str) -> Optional[dict[str, Any]]:
    train_number = _safe_string(
        _coalesce(
            item.get("train_number"),
            item.get("train_no"),
            item.get("train_num"),
            item.get("number"),
            item.get("id"),
        )
    )
    train_name = _safe_string(
        _coalesce(
            item.get("train_name"),
            item.get("name"),
            item.get("train"),
            item.get("trainName"),
        )
    )
    source_name, source_code = _coalesce_station(
        item.get("source"),
        item.get("from"),
        item.get("from_station"),
        item.get("source_station"),
        item.get("sourceStation"),
        item.get("source_name"),
        item.get("sourceName"),
        item.get("src"),
        item.get("source_code"),
        item.get("sourceCode"),
        item.get("src_code"),
    )
    destination_name, destination_code = _coalesce_station(
        item.get("destination"),
        item.get("to"),
        item.get("to_station"),
        item.get("destination_station"),
        item.get("destinationStation"),
        item.get("destination_name"),
        item.get("destinationName"),
        item.get("dest"),
        item.get("destination_code"),
        item.get("destinationCode"),
        item.get("dest_code"),
    )

    if not train_name and not train_number:
        return None

    fare_per_seat = _safe_float(
        _coalesce(
            item.get("fare_per_seat"),
            item.get("fare"),
            item.get("ticket_fare"),
            item.get("ticketFare"),
            item.get("price"),
            item.get("amount"),
        ),
        default=0.0,
    )
    seats_available = _safe_int(
        _coalesce(
            item.get("seats_available"),
            item.get("available_seats"),
            item.get("availableSeats"),
            item.get("seat_available"),
            item.get("seatAvailable"),
            item.get("availability"),
            item.get("available"),
        ),
        default=0,
    )

    normalized = {
        "id": train_number or train_name or f"{source}-{destination}-{travel_date}",
        "train_id": _safe_int(train_number, default=0) or None,
        "train_number": train_number,
        "train_name": train_name or f"Train {train_number or ''}".strip(),
        "source": source_name or source.title(),
        "source_code": source_code,
        "destination": destination_name or destination.title(),
        "destination_code": destination_code,
        "travel_date": _safe_date(
            _coalesce(
                item.get("travel_date"),
                item.get("journey_date"),
                item.get("date"),
                item.get("running_date"),
            ),
            travel_date,
        ),
        "departure_time": _safe_time(
            _coalesce(
                item.get("departure_time"),
                item.get("departure"),
                item.get("depart_time"),
                item.get("departureTime"),
                item.get("src_departure_time"),
            )
        ),
        "arrival_time": _safe_time(
            _coalesce(
                item.get("arrival_time"),
                item.get("arrival"),
                item.get("arrive_time"),
                item.get("arrivalTime"),
                item.get("dest_arrival_time"),
            )
        ),
        "seats_available": seats_available,
        "fare_per_seat": round(fare_per_seat, 2),
        "data_source": "api",
    }
    normalized["total_fare"] = round(normalized["fare_per_seat"], 2)
    return normalized


def _dedupe_trains(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[dict[str, Any]] = []

    for train in results:
        key = (
            str(train.get("train_number") or train.get("train_name") or ""),
            normalize_station_name(train.get("source") or ""),
            normalize_station_name(train.get("destination") or ""),
            str(train.get("travel_date") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(train)
    return deduped


def _filter_route_matches(results: list[dict[str, Any]], source: str, destination: str) -> list[dict[str, Any]]:
    if not results:
        return []

    ranked: list[tuple[dict[str, Any], float, float]] = []

    for item in results:
        source_score = max(
            station_match_score(source, item.get("source") or ""),
            station_match_score(source, item.get("source_code") or ""),
            station_match_score(
                source,
                f"{item.get('source') or ''} {item.get('source_code') or ''}".strip(),
            ),
        )
        destination_score = max(
            station_match_score(destination, item.get("destination") or ""),
            station_match_score(destination, item.get("destination_code") or ""),
            station_match_score(
                destination,
                f"{item.get('destination') or ''} {item.get('destination_code') or ''}".strip(),
            ),
        )

        if source_score < 0.5 or destination_score < 0.5:
            continue

        ranked.append((item, source_score, destination_score))

    ranked.sort(
        key=lambda pair: (
            -(pair[1] + pair[2]),
            pair[0].get("departure_time") or "99:99",
            pair[0].get("train_name") or "",
        )
    )
    return [item for item, _, _ in ranked]


def _filter_train_name(results: list[dict[str, Any]], train_name: str) -> list[dict[str, Any]]:
    ranked: list[tuple[dict[str, Any], float]] = []
    for item in results:
        score = max(
            text_match_score(train_name, item.get("train_name") or ""),
            text_match_score(train_name, item.get("train_number") or ""),
        )
        if score >= 0.62:
            ranked.append((item, score))

    ranked.sort(key=lambda pair: (-pair[1], pair[0].get("departure_time") or "99:99"))
    return [item for item, _ in ranked]


def _get_mock_trains(source: str, destination: str, travel_date: str) -> list[dict[str, Any]]:
    """Generates realistic mock train data for demonstration."""
    train_templates = [
        ("12951", "Rajdhani Express", "16:40", "08:35", 2450.0),
        ("12002", "Shatabdi Express", "06:00", "11:50", 1100.0),
        ("12260", "Duronto Express", "20:15", "12:45", 1850.0),
        ("12424", "Garib Rath", "13:55", "05:00", 950.0),
        ("12925", "Paschim Express", "11:30", "14:45", 650.0),
        ("22415", "Vande Bharat", "06:00", "14:10", 1600.0),
    ]
    
    import random
    results = []
    for number, name, dep, arr, fare in train_templates:
        results.append({
            "id": f"MOCK-{number}",
            "train_id": int(number),
            "train_number": number,
            "train_name": name,
            "source": source.title(),
            "destination": destination.title(),
            "travel_date": travel_date,
            "departure_time": dep,
            "arrival_time": arr,
            "seats_available": random.randint(5, 150),
            "fare_per_seat": fare,
            "total_fare": fare,
            "data_source": "mock",
        })
    return results


def _request_api(source: str, destination: str, travel_date: str) -> list[dict[str, Any]]:
    is_placeholder = not RAPIDAPI_KEY or str(RAPIDAPI_KEY).startswith("your_")
    
    if RAPIDAPI_MOCK or is_placeholder:
        return _get_mock_trains(source, destination, travel_date)

    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }
    param_variants = [
        {"source": source, "destination": destination, "travel_date": travel_date},
        {"source": source, "destination": destination, "date": travel_date},
        {"source": source, "destination": destination, "journey_date": travel_date},
        {"source": source, "destination": destination},
    ]

    last_error: Optional[str] = None
    for params in param_variants:
        try:
            response = requests.get(RAPIDAPI_TRAIN_ENDPOINT, headers=headers, params=params, timeout=12)
        except requests.RequestException as exc:
            last_error = str(exc)
            continue

        if response.status_code >= 400:
            last_error = f"RapidAPI returned HTTP {response.status_code}"
            continue

        try:
            payload = response.json()
        except ValueError as exc:
            last_error = f"RapidAPI returned invalid JSON: {exc}"
            continue

        normalized: list[dict[str, Any]] = []
        for candidate_list in _candidate_lists(payload):
            for item in candidate_list:
                mapped = _normalize_train(item, source, destination, travel_date)
                if mapped:
                    normalized.append(mapped)

        if normalized:
            return _dedupe_trains(normalized)

    if last_error:
        raise TrainSearchError(last_error)
    return []


def search_trains(source: str, destination: str, travel_date: str, seats: int = 1, train_name: Optional[str] = None) -> list[dict[str, Any]]:
    results = _request_api(source, destination, travel_date)
    filtered = _filter_route_matches(results, source, destination)

    if train_name:
        filtered = _filter_train_name(filtered, train_name)

    normalized_results: list[dict[str, Any]] = []
    for item in filtered:
        cloned = dict(item)
        cloned["seats_available"] = max(_safe_int(cloned.get("seats_available"), default=0), 0)
        cloned["fare_per_seat"] = round(_safe_float(cloned.get("fare_per_seat"), default=0.0), 2)
        cloned["total_fare"] = round(cloned["fare_per_seat"] * max(seats, 1), 2)
        normalized_results.append(cloned)

    return normalized_results


def find_best_train_match(query: str, results: list[dict[str, Any]], minimum_score: float = 0.7) -> Optional[dict[str, Any]]:
    ranked: list[tuple[dict[str, Any], float]] = []
    for result in results:
        score = max(
            text_match_score(query, result.get("train_name") or ""),
            text_match_score(query, result.get("train_number") or ""),
        )
        if score >= minimum_score:
            ranked.append((result, score))

    ranked.sort(key=lambda pair: (-pair[1], pair[0].get("departure_time") or "99:99"))
    return ranked[0][0] if ranked else None
