"""
Resolve place names to country (ISO 3166-1 alpha-2) via Nominatim.
Used to set relocation budget currency (e.g. USD for US, EUR otherwise) without hardcoding cities.
"""

import time
from typing import Any

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "RelocationConcierge/1.0 (Employee Relocation; country lookup)"
# Nominatim usage policy: 1 req/sec
_MIN_REQUEST_INTERVAL = 1.1
_last_request_time: float = 0.0


def get_country_code(place_name: str) -> str | None:
    """
    Geocode a place name (city, town, etc.) and return its ISO country code (e.g. 'us', 'de').
    Uses Nominatim (OpenStreetMap); free, no API key. Returns None on failure or no result.
    """
    global _last_request_time
    place = (place_name or "").strip()
    if not place:
        return None

    # Respect Nominatim 1 req/sec policy
    now = time.monotonic()
    elapsed = now - _last_request_time
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.monotonic()

    try:
        with httpx.Client(timeout=10.0, headers={"User-Agent": USER_AGENT}) as client:
            r = client.get(
                NOMINATIM_URL,
                params={
                    "q": place,
                    "format": "json",
                    "limit": 1,
                    "addressdetails": 1,
                },
            )
            r.raise_for_status()
            results: list[Any] = r.json()
    except Exception:
        return None

    if not results:
        return None
    first = results[0]
    address = first.get("address")
    if not isinstance(address, dict):
        return None
    code = address.get("country_code")
    if isinstance(code, str) and len(code) == 2:
        return code.lower()
    return None


def is_place_in_us(place_name: str) -> bool:
    """Return True if the place is in the United States (USD for budget)."""
    return get_country_code(place_name) == "us"
