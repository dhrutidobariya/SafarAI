import re

from rapidfuzz import fuzz


_ALIASES = {
    "ahmedabad": ["ahmedabad", "adi"],
    "bangalore": ["bengaluru", "bangalore", "sbc"],
    "bengaluru": ["bengaluru", "bangalore", "sbc"],
    "bombay": ["mumbai", "mumbai central", "mumbai csmt"],
    "calcutta": ["kolkata", "howrah"],
    "chennai": ["chennai", "chennai central", "mas"],
    "delhi": ["delhi", "new delhi", "old delhi", "ndls"],
    "delh": ["delhi", "new delhi"],
    "delhu": ["delhi", "new delhi"],
    "madras": ["chennai", "chennai central"],
    "mumbai": ["mumbai", "mumbai central", "mumbai csmt", "bombay"],
    "mubai": ["mumbai", "mumbai central"],
    "mumabi": ["mumbai", "mumbai central"],
    "new delhi": ["new delhi", "delhi", "ndls"],
    "surat": ["surat", "st"],
}


def normalize_station_name(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (value or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def expand_station_query(query: str) -> list[str]:
    normalized = normalize_station_name(query)
    if not normalized:
        return []

    expanded = [normalized]
    for alias in _ALIASES.get(normalized, []):
        alias_normalized = normalize_station_name(alias)
        if alias_normalized and alias_normalized not in expanded:
            expanded.append(alias_normalized)
    return expanded


def text_match_score(query: str, candidate: str) -> float:
    query_normalized = normalize_station_name(query)
    candidate_normalized = normalize_station_name(candidate)
    if not query_normalized or not candidate_normalized:
        return 0.0

    if query_normalized == candidate_normalized:
        return 1.0

    token_score = fuzz.token_set_ratio(query_normalized, candidate_normalized) / 100.0
    partial_score = fuzz.partial_ratio(query_normalized, candidate_normalized) / 100.0
    simple_score = fuzz.ratio(query_normalized, candidate_normalized) / 100.0
    return round(max(token_score, partial_score * 0.96, simple_score * 0.92), 4)


def station_match_score(query: str, candidate: str) -> float:
    candidate_normalized = normalize_station_name(candidate)
    if not candidate_normalized:
        return 0.0

    best_score = 0.0
    for query_variant in expand_station_query(query):
        if query_variant == candidate_normalized:
            best_score = max(best_score, 1.0)
            continue

        if query_variant and query_variant in candidate_normalized:
            best_score = max(best_score, 0.96)

        query_tokens = set(query_variant.split())
        candidate_tokens = set(candidate_normalized.split())
        token_overlap = len(query_tokens & candidate_tokens) / max(len(query_tokens), len(candidate_tokens), 1)
        sequence_score = text_match_score(query_variant, candidate_normalized)
        best_score = max(best_score, sequence_score * 0.8 + token_overlap * 0.2)

    return round(best_score, 4)


def resolve_station_candidates(query: str, candidates: list[str], *, limit: int = 4, minimum_score: float = 0.7) -> list[str]:
    seen: set[str] = set()
    ranked: list[tuple[str, float]] = []

    for candidate in candidates:
        normalized_candidate = normalize_station_name(candidate)
        if not normalized_candidate or normalized_candidate in seen:
            continue
        seen.add(normalized_candidate)

        score = station_match_score(query, candidate)
        if score >= minimum_score:
            ranked.append((candidate, score))

    ranked.sort(key=lambda item: (-item[1], len(normalize_station_name(item[0])), item[0]))
    return [candidate for candidate, _ in ranked[:limit]]
