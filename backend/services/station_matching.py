import re

from rapidfuzz import fuzz, process


def normalize_station_name(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (value or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


_STATION_ALIASES_RAW = {
    "Ahmedabad": ["ahmedabad", "adi", "ahmedabad junction", "ahmedabad jn", "kalupur"],
    "Ajmer": ["ajmer", "aii", "ajmer junction", "ajmer jn"],
    "Amritsar": ["amritsar", "asr", "amritsar junction"],
    "Bengaluru": [
        "bengaluru",
        "bangalore",
        "banglore",
        "bengluru",
        "beglaru",
        "blr",
        "sbc",
        "k sr bengaluru",
        "krantivira sangolli rayanna",
    ],
    "Bhopal": ["bhopal", "bpl", "bhopal junction", "rani kamlapati", "rkmp"],
    "Bhubaneswar": ["bhubaneswar", "bbs", "bbsr"],
    "Chandigarh": ["chandigarh", "cdg", "chandigarh junction"],
    "Chennai": ["chennai", "madras", "mas", "chennai central", "mgr chennai central"],
    "Coimbatore": ["coimbatore", "cbe", "coimbatore junction"],
    "Ernakulam": ["ernakulam", "kochi", "cochin", "ers", "ekm", "ernakulam junction"],
    "Goa": ["goa", "madgaon", "margao", "mao", "vasco", "vasco da gama", "vsg"],
    "Guwahati": ["guwahati", "ghy", "guwahati junction"],
    "Hyderabad": ["hyderabad", "hyd", "secunderabad", "sc", "kacheguda", "kcg"],
    "Indore": ["indore", "indb", "indore junction"],
    "Jaipur": ["jaipur", "jp", "jaipur junction"],
    "Jammu": ["jammu", "jammu tawi", "jat"],
    "Jodhpur": ["jodhpur", "ju", "jodhpur junction"],
    "Kanpur": ["kanpur", "cnb", "kanpur central"],
    "Kolkata": ["kolkata", "calcutta", "howrah", "hwh", "sealdah", "sdah"],
    "Kota": ["kota", "kta", "kota junction"],
    "Lucknow": ["lucknow", "lko", "lucknow charbagh", "charbagh"],
    "Madurai": ["madurai", "mdu", "madurai junction"],
    "Mumbai": [
        "mumbai",
        "bombay",
        "mumabi",
        "mubai",
        "cst",
        "csmt",
        "mmct",
        "bdts",
        "ltt",
        "dr",
        "dadar",
        "mumbai central",
        "mumbai csmt",
        "lokmanya tilak terminus",
        "bandra terminus",
    ],
    "Mysuru": ["mysuru", "mysore", "mys", "mysuru junction"],
    "Nagpur": ["nagpur", "nagpore", "ngp", "nagpur junction"],
    "New Delhi": [
        "new delhi",
        "delhi",
        "ndls",
        "dli",
        "delh",
        "delhu",
        "deli",
        "old delhi",
        "delhi junction",
    ],
    "Patna": ["patna", "pnbe", "patna jn", "patliputra", "ppta"],
    "Prayagraj": ["prayagraj", "allahabad", "ald", "prayag"],
    "Pune": ["pune", "pune junction", "pune jn", "poona"],
    "Raipur": ["raipur", "r", "raipur junction"],
    "Ranchi": ["ranchi", "rnc", "ranchi junction"],
    "Surat": ["surat", "st", "surt", "surat junction"],
    "Thiruvananthapuram": ["thiruvananthapuram", "trivandrum", "tvc", "trivandrum central"],
    "Tiruchirappalli": ["tiruchirappalli", "trichy", "tpj"],
    "Udaipur": ["udaipur", "udz", "udaipur city"],
    "Vadodara": ["vadodara", "baroda", "brc", "vadodara junction"],
    "Varanasi": ["varanasi", "banaras", "benares", "bsb", "bsbs"],
    "Vijayawada": ["vijayawada", "bza", "vijaywada"],
    "Visakhapatnam": ["visakhapatnam", "vizag", "vskp"],
}

_FUZZY_WORDS = {
    "seat": ["seta", "seet", "siet", "sit", "seats", "sheet"],
    "train": ["trian", "trai", "tarin", "trains"],
    "available": ["avilable", "avlbl", "avail", "avalaible", "availabel"],
    "ticket": ["tiket", "tickit", "tikcet", "tickets"],
}

_NON_STATION_WORDS = {
    "a",
    "an",
    "and",
    "any",
    "as",
    "available",
    "availability",
    "book",
    "booking",
    "bookings",
    "class",
    "date",
    "details",
    "find",
    "for",
    "from",
    "help",
    "in",
    "is",
    "journey",
    "me",
    "my",
    "of",
    "on",
    "passenger",
    "pay",
    "payment",
    "please",
    "proceed",
    "route",
    "search",
    "seat",
    "seats",
    "show",
    "station",
    "status",
    "the",
    "ticket",
    "tickets",
    "to",
    "train",
    "trains",
    "travel",
    "trip",
    "want",
    "with",
}

_DATE_WORDS = {
    "today",
    "tomorrow",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "next",
    "this",
}


def _build_station_alias_maps() -> tuple[dict[str, list[str]], dict[str, str]]:
    canonical_to_aliases: dict[str, list[str]] = {}
    alias_to_canonical: dict[str, str] = {}

    for canonical, aliases in _STATION_ALIASES_RAW.items():
        normalized_aliases: list[str] = []
        for alias in [canonical, *aliases]:
            normalized_alias = normalize_station_name(alias)
            if not normalized_alias or normalized_alias in normalized_aliases:
                continue
            normalized_aliases.append(normalized_alias)
            alias_to_canonical[normalized_alias] = canonical
        canonical_to_aliases[canonical] = normalized_aliases

    return canonical_to_aliases, alias_to_canonical


_CANONICAL_TO_ALIASES, _ALIAS_TO_CANONICAL = _build_station_alias_maps()
_STATION_CHOICES = sorted(_ALIAS_TO_CANONICAL)


def fuzzy_normalize_input(text: str) -> str:
    lowered = (text or "").lower()
    for official, variants in _FUZZY_WORDS.items():
        for variant in variants:
            lowered = re.sub(rf"\b{re.escape(variant)}\b", official, lowered)
    return lowered


def clean_station_phrase(text: str) -> str:
    lowered = fuzzy_normalize_input(text)
    lowered = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", lowered)
    lowered = re.sub(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", " ", lowered)
    lowered = re.sub(r"\bday after tomorrow\b", " ", lowered)
    lowered = re.sub(r"\b\d+\s*(?:seat|ticket)s?\b", " ", lowered)
    lowered = re.sub(r"\b(?:seat|ticket)s?\s*\d+\b", " ", lowered)

    words = normalize_station_name(lowered).split()
    filtered_words = [
        word
        for word in words
        if word not in _NON_STATION_WORDS and word not in _DATE_WORDS and not word.isdigit()
    ]
    return " ".join(filtered_words).strip()


def _canonical_station_name(query: str, *, minimum_score: int = 74, allow_fuzzy: bool = True) -> str | None:
    cleaned = clean_station_phrase(query)
    if not cleaned:
        return None

    direct = _ALIAS_TO_CANONICAL.get(cleaned)
    if direct:
        return direct

    if not allow_fuzzy:
        return None

    best_match = process.extractOne(cleaned, _STATION_CHOICES, scorer=fuzz.WRatio)
    if best_match and best_match[1] >= minimum_score:
        return _ALIAS_TO_CANONICAL[best_match[0]]

    return None


def match_station(query: str, minimum_score: int = 74) -> str | None:
    return _canonical_station_name(query, minimum_score=minimum_score, allow_fuzzy=True)


def extract_station_mentions(text: str, *, limit: int = 2, minimum_score: int = 74) -> list[str]:
    cleaned = clean_station_phrase(text)
    if not cleaned:
        return []

    token_count = len(cleaned.split())
    results = process.extract(
        cleaned,
        _STATION_CHOICES,
        scorer=fuzz.WRatio,
        limit=1 if token_count <= 1 else max(limit * 4, limit),
    )

    ranked_stations: list[tuple[str, float, int]] = []
    seen: set[str] = set()
    for alias, score, _ in results:
        if score < minimum_score:
            continue
        canonical = _ALIAS_TO_CANONICAL[alias]
        if canonical in seen:
            continue
        seen.add(canonical)
        alias_positions = [cleaned.find(candidate_alias) for candidate_alias in _CANONICAL_TO_ALIASES.get(canonical, [])]
        alias_positions = [position for position in alias_positions if position >= 0]
        first_position = min(alias_positions) if alias_positions else len(cleaned) + len(ranked_stations)
        ranked_stations.append((canonical, score, first_position))
        if len(ranked_stations) >= limit:
            break

    ranked_stations.sort(key=lambda item: (item[2], -item[1], item[0]))
    return [canonical for canonical, _, _ in ranked_stations[:limit]]


def map_to_official_city(name: str) -> str:
    canonical = _canonical_station_name(name, minimum_score=74, allow_fuzzy=True)
    if canonical:
        return canonical

    cleaned = clean_station_phrase(name)
    if cleaned:
        return cleaned.title()

    fallback = normalize_station_name(name)
    return fallback.title() if fallback else name


def expand_station_query(query: str) -> list[str]:
    variants: list[str] = []

    for candidate in (normalize_station_name(query), clean_station_phrase(query)):
        if candidate and candidate not in variants:
            variants.append(candidate)

    canonical = _canonical_station_name(query, minimum_score=88, allow_fuzzy=True)
    if canonical:
        for alias in _CANONICAL_TO_ALIASES.get(canonical, []):
            if alias not in variants:
                variants.append(alias)

    return variants


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
    weighted_score = fuzz.WRatio(query_normalized, candidate_normalized) / 100.0
    return round(max(weighted_score, token_score * 0.99, partial_score * 0.96, simple_score * 0.92), 4)


def station_match_score(query: str, candidate: str) -> float:
    query_variants = expand_station_query(query)
    candidate_variants = expand_station_query(candidate)

    if not query_variants:
        query_variants = [normalize_station_name(query)]
    if not candidate_variants:
        candidate_variants = [normalize_station_name(candidate)]

    best_score = 0.0
    for query_variant in query_variants:
        for candidate_variant in candidate_variants:
            if not query_variant or not candidate_variant:
                continue

            if query_variant == candidate_variant:
                best_score = max(best_score, 1.0)
                continue

            if query_variant in candidate_variant or candidate_variant in query_variant:
                best_score = max(best_score, 0.96)

            query_tokens = set(query_variant.split())
            candidate_tokens = set(candidate_variant.split())
            token_overlap = len(query_tokens & candidate_tokens) / max(len(query_tokens), len(candidate_tokens), 1)
            sequence_score = text_match_score(query_variant, candidate_variant)
            best_score = max(best_score, sequence_score * 0.82 + token_overlap * 0.18)

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
