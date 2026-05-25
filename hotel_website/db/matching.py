"""Utilities for matching hotels across providers: name normalisation,
similarity scoring, and great-circle distance.
"""
import math
import re
import unicodedata
from difflib import SequenceMatcher

_NOISE_TOKENS = {
    "hotel", "hotels", "resort", "resorts", "spa", "suites", "suite",
    "inn", "by", "the", "and", "of", "a", "an", "&",
    "international", "intl", "boutique", "luxury", "grand",
    "apartments", "apartment", "lodge", "lodges", "villa", "villas",
    "palace", "garden", "gardens", "club", "house",
}

_SEPARATORS = re.compile(r"[\s\-_/.,'\"&()\[\]:;!?]+")


def normalise_name(raw: str) -> str:
    """Lowercase, strip diacritics + punctuation + common hotel noise words."""
    if not raw:
        return ""
    text = unicodedata.normalize("NFKD", raw)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = _SEPARATORS.sub(" ", text).strip()
    tokens = [t for t in text.split() if t and t not in _NOISE_TOKENS]
    return " ".join(tokens) if tokens else text


def name_similarity(a: str, b: str) -> float:
    """Return similarity in [0, 1]. Uses ratcliff/obershelp on normalised names."""
    na, nb = normalise_name(a), normalise_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def haversine_meters(lat1, lon1, lat2, lon2) -> float | None:
    """Great-circle distance in metres. Returns None if any coordinate is missing."""
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
    except (TypeError, ValueError):
        return None
    r = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def distance_score(distance_m: float | None, buffer_m: float = 100.0, falloff_m: float = 1000.0) -> float:
    """Map a distance to a [0, 1] score.

    - <= buffer_m       → 1.0  (same location)
    - >= buffer_m+falloff_m → 0.0
    - linear in between
    """
    if distance_m is None:
        return 0.0
    if distance_m <= buffer_m:
        return 1.0
    if distance_m >= buffer_m + falloff_m:
        return 0.0
    return 1.0 - (distance_m - buffer_m) / falloff_m


def combined_score(name_score: float, dist_score: float, name_weight: float = 0.6) -> float:
    """Weighted combination of name + distance scores."""
    return name_weight * name_score + (1.0 - name_weight) * dist_score
