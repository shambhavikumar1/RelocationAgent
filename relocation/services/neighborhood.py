"""
Neighborhood shortlisting via API/tool.
Uses (1) NEIGHBORHOOD_API_URL if set, (2) OpenStreetMap (Nominatim + Overpass) for
real neighborhood/suburb data by geolocation, (3) Teleport API for city scores as
fallback, (4) mock data only if APIs fail.
"""

import math
import os
import time
from dataclasses import dataclass

import httpx

# OSM amenity/leisure tag -> highlight label (for neighborhood highlights from Overpass)
_AMENITY_TO_HIGHLIGHT: dict[str, str] = {
    "restaurant": "Restaurants",
    "fast_food": "Restaurants",
    "cafe": "Cafes",
    "pub": "Nightlife",
    "bar": "Nightlife",
    "park": "Parks",
    "garden": "Parks",
    "library": "Culture",
    "theatre": "Culture",
    "museum": "Culture",
    "arts_centre": "Culture",
    "bus_station": "Transit",
    "train_station": "Transit",
    "subway_entrance": "Transit",
    "school": "Schools",
    "university": "Schools",
    "college": "Schools",
    "kindergarten": "Schools",
    "marketplace": "Shopping",
    "supermarket": "Shopping",
    "convenience": "Shopping",
    "pharmacy": "Healthcare",
    "hospital": "Healthcare",
    "clinic": "Healthcare",
    "doctors": "Healthcare",
    "place_of_worship": "Community",
    "community_centre": "Community",
    "fitness_centre": "Fitness",
    "sports_centre": "Sports",
}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance in km between two points."""
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _element_center(el: dict) -> tuple[float, float] | None:
    """Get (lat, lon) for an Overpass node or way (with center)."""
    if el.get("type") == "node":
        lat, lon = el.get("lat"), el.get("lon")
        if lat is not None and lon is not None:
            return (float(lat), float(lon))
    if el.get("type") == "way" and "center" in el:
        c = el["center"]
        return (float(c["lat"]), float(c["lon"]))
    if el.get("type") == "way" and "bounds" in el:
        b = el["bounds"]
        return ((b["minlat"] + b["maxlat"]) / 2, (b["minlon"] + b["maxlon"]) / 2)
    return None

# OpenStreetMap: Nominatim (geocode) + Overpass (query places) - free, no API key
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Try multiple Overpass servers; 504/timeouts are common under load
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
OVERPASS_TIMEOUT = 45.0  # client timeout (seconds); server may still return 504
# Nominatim usage policy: 1 req/sec; use a descriptive User-Agent
USER_AGENT = "RelocationConcierge/1.0 (Employee Relocation; neighborhood lookup)"

# Teleport API (free, no API key required)
TELEPORT_BASE = "https://api.teleport.org/api"

# City name -> Teleport urban area slug (expand as needed)
TELEPORT_SLUGS: dict[str, str] = {
    "berlin": "berlin",
    "london": "london",
    "munich": "munich",
    "münchen": "munich",
    "amsterdam": "amsterdam",
    "paris": "paris",
    "vienna": "vienna",
    "wien": "vienna",
    "dublin": "dublin",
    "madrid": "madrid",
    "barcelona": "barcelona",
    "rome": "rome",
    "milan": "milan",
    "brussels": "brussels",
    "zurich": "zurich",
    "copenhagen": "copenhagen",
    "stockholm": "stockholm",
    "oslo": "oslo",
    "helsinki": "helsinki",
    "lisbon": "lisbon",
    "prague": "prague",
    "warsaw": "warsaw",
    "budapest": "budapest",
    "athens": "athens",
    "new york": "new-york",
    "san francisco": "san-francisco-bay-area",
    "los angeles": "los-angeles",
    "chicago": "chicago",
    "boston": "boston",
    "seattle": "seattle",
    "washington": "washington-dc",
    "atlanta": "atlanta",
    "tampa": "tampa",
    "miami": "miami",
    "dallas": "dallas",
    "houston": "houston",
    "toronto": "toronto",
    "sydney": "sydney",
    "melbourne": "melbourne",
    "singapore": "singapore",
    "tokyo": "tokyo",
    "hong kong": "hong-kong",
}


@dataclass
class Neighborhood:
    name: str
    area: str
    city: str
    score: float
    highlights: list[str]
    avg_rent_1bed_eur: int | None


def _fetch_osm_neighborhoods(city: str, city_display: str, max_results: int) -> list[Neighborhood]:
    """
    Get neighborhoods/suburbs from OpenStreetMap via Nominatim (geocode city to bbox)
    + Overpass (query place=suburb|neighbourhood|quarter|district in bbox).
    Free, no API key. Returns real place names from OSM; no score/rent data.
    """
    if not (city or city_display):
        return []
    query = (city or city_display).strip()
    try:
        with httpx.Client(timeout=10.0, headers={"User-Agent": USER_AGENT}) as client:
            r = client.get(
                NOMINATIM_URL,
                params={"q": query, "format": "json", "limit": 1},
            )
            r.raise_for_status()
            results = r.json()
        if not results:
            return []
        first = results[0]
        # boundingbox: [south, north, west, east] as strings
        bbox = first.get("boundingbox")
        if not bbox or len(bbox) < 4:
            return []
        south, north, west, east = bbox[0], bbox[1], bbox[2], bbox[3]
        time.sleep(1.1)  # Nominatim policy: 1 req/sec
    except Exception:
        return []

    # Overpass: nodes and ways with place=suburb|neighbourhood|quarter|district in bbox
    overpass_query = f"""
[out:json][timeout:15];
(
  node["place"~"suburb|neighbourhood|quarter|district"]({south},{west},{north},{east});
  way["place"~"suburb|neighbourhood|quarter|district"]({south},{west},{north},{east});
);
out center;
"""
    data: dict = {}
    for overpass_url in OVERPASS_URLS:
        try:
            with httpx.Client(timeout=OVERPASS_TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
                r = client.post(overpass_url, content=overpass_query.encode("utf-8"))
                if r.status_code == 504 or r.status_code == 524:
                    continue  # try next server
                r.raise_for_status()
                data = r.json()
                break
        except (httpx.TimeoutException, httpx.HTTPStatusError):
            continue
        except Exception:
            continue
    if not data:
        return []

    elements = data.get("elements", [])
    seen_names: set[str] = set()
    # Build list of (name, place, center_lat, center_lon) for each neighborhood
    neighborhood_centers: list[tuple[str, str, float, float]] = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name or name in seen_names:
            continue
        center = _element_center(el)
        if not center:
            continue
        seen_names.add(name)
        place = tags.get("place", "")
        neighborhood_centers.append((name, place.replace("_", " ").title() or "Area", center[0], center[1]))
        if len(neighborhood_centers) >= max_results:
            break

    if not neighborhood_centers:
        return []

    # Second Overpass query: amenities and leisure in same bbox (for highlights)
    amenity_query = f"""
[out:json][timeout:15];
(
  node["amenity"]({south},{west},{north},{east});
  node["leisure"]({south},{west},{north},{east});
);
out;
"""
    highlights_by_idx: list[dict[str, int]] = [{} for _ in neighborhood_centers]
    amenity_data: dict = {"elements": []}
    for overpass_url in OVERPASS_URLS:
        try:
            with httpx.Client(timeout=OVERPASS_TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
                r = client.post(overpass_url, content=amenity_query.encode("utf-8"))
                if r.status_code in (504, 524):
                    continue
                r.raise_for_status()
                amenity_data = r.json()
                break
        except Exception:
            continue

    for el in amenity_data.get("elements", []):
        if el.get("type") != "node":
            continue
        lat, lon = el.get("lat"), el.get("lon")
        if lat is None or lon is None:
            continue
        tags = el.get("tags", {})
        label = _AMENITY_TO_HIGHLIGHT.get(tags.get("amenity") or tags.get("leisure") or "")
        if not label:
            continue
        # Assign to nearest neighborhood within 2.5 km
        best_idx, best_km = None, 2.5
        for idx, (_, _, nc_lat, nc_lon) in enumerate(neighborhood_centers):
            km = _haversine_km(nc_lat, nc_lon, float(lat), float(lon))
            if km < best_km:
                best_km, best_idx = km, idx
        if best_idx is not None:
            highlights_by_idx[best_idx][label] = highlights_by_idx[best_idx].get(label, 0) + 1

    city_name = (city or city_display).strip() or ""
    out = []
    for idx, (name, area, _clat, _clon) in enumerate(neighborhood_centers):
        counts = highlights_by_idx[idx]
        highlights = [label for label, _ in sorted(counts.items(), key=lambda x: -x[1])[:4]]
        out.append(
            Neighborhood(
                name=name,
                area=area,
                city=city_name,
                score=7.5,
                highlights=highlights if highlights else [],
                avg_rent_1bed_eur=None,
            )
        )
    return out


def _teleport_slug(city: str) -> str | None:
    """Resolve city name to Teleport urban area slug (search API if not in map)."""
    key = city.lower().strip() if city else ""
    if not key:
        return None
    if key in TELEPORT_SLUGS:
        return TELEPORT_SLUGS[key]
    try:
        with httpx.Client(timeout=8.0) as client:
            r = client.get(f"{TELEPORT_BASE}/cities/", params={"search": city})
            r.raise_for_status()
            data = r.json()
        # Response: _embedded["city:search-results"] -> ["matching_alternate_names"] or link to urban area
        for item in data.get("_embedded", {}).get("city:search-results", [])[:3]:
            links = item.get("_links", {})
            ua = links.get("city:urban_area")
            if ua:
                href = ua.get("href", "")
                # href like "https://api.teleport.org/api/urban_areas/slug:berlin/"
                if "urban_areas/slug:" in href:
                    slug = href.split("urban_areas/slug:")[-1].rstrip("/")
                    return slug
    except Exception:
        pass
    return None


def _fetch_teleport(city: str, city_display: str, max_results: int) -> list[Neighborhood]:
    """
    Use Teleport API (free) for city scores and quality-of-life categories.
    Returns one city-overview row from real API data, then up to (max_results-1)
    well-known districts from a static list so we have both API data and area names.
    """
    slug = _teleport_slug(city or city_display)
    if not slug:
        return []

    out: list[Neighborhood] = []
    try:
        with httpx.Client(timeout=10.0) as client:
            # Scores: Housing, Cost of Living, Safety, etc. (0-10)
            resp = client.get(f"{TELEPORT_BASE}/urban_areas/slug:{slug}/scores/")
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    categories = data.get("categories", [])
    highlights = [c["name"] for c in categories if c.get("score_out_of_10", 0) >= 6.0][:6]
    if not highlights:
        highlights = [c["name"] for c in categories[:4]]
    avg_score = (
        sum(c.get("score_out_of_10", 0) for c in categories) / len(categories)
        if categories else 0
    )
    avg_score = round(avg_score * 10) / 10  # one decimal

    # Optional: cost/salary details for rent hint (Teleport details format may vary)
    avg_rent: int | None = None
    try:
        with httpx.Client(timeout=8.0) as client:
            det = client.get(f"{TELEPORT_BASE}/urban_areas/slug:{slug}/details/")
            det.raise_for_status()
            details = det.json()
        for cat in details.get("categories", []):
            for item in cat.get("data", []):
                val = item.get("currency_dollar_value") or item.get("float_value") or item.get("value")
                if val is not None and "apartment" in (item.get("id") or "").lower():
                    try:
                        avg_rent = int(float(val))
                        break
                    except (TypeError, ValueError):
                        pass
            if avg_rent is not None:
                break
    except Exception:
        pass

    # First row: city overview from Teleport (real API data)
    out.append(
        Neighborhood(
            name=f"{city_display or city} (overview)",
            area="City",
            city=city_display or city,
            score=avg_score,
            highlights=highlights,
            avg_rent_1bed_eur=avg_rent,
        )
    )

    # Add known districts for this city (static list) so we show neighborhood names
    districts = _known_districts_for_city(city or city_display)
    for d in districts[: max_results - 1]:
        out.append(
            Neighborhood(
                name=d["name"],
                area=d.get("area", ""),
                city=city_display or city,
                score=round(avg_score * 0.98, 1),  # slight variance
                highlights=highlights[:3],
                avg_rent_1bed_eur=avg_rent,
            )
        )
    return out[:max_results]


def _known_districts_for_city(city: str) -> list[dict]:
    """Well-known district names per city (for display; scores come from Teleport)."""
    key = (city or "").lower().strip()
    districts_by_city: dict[str, list[dict]] = {
        "berlin": [
            {"name": "Mitte", "area": "Central"},
            {"name": "Kreuzberg", "area": "Central"},
            {"name": "Prenzlauer Berg", "area": "East"},
            {"name": "Charlottenburg", "area": "West"},
            {"name": "Friedrichshain", "area": "East"},
        ],
        "munich": [
            {"name": "Schwabing", "area": "North"},
            {"name": "Maxvorstadt", "area": "Central"},
            {"name": "Glockenbach", "area": "Central"},
            {"name": "Haidhausen", "area": "East"},
            {"name": "Sendling", "area": "South"},
        ],
        "london": [
            {"name": "Shoreditch", "area": "East"},
            {"name": "Camden", "area": "North"},
            {"name": "Clapham", "area": "South"},
            {"name": "Islington", "area": "North"},
            {"name": "Bermondsey", "area": "South"},
        ],
        "amsterdam": [
            {"name": "Jordaan", "area": "Central"},
            {"name": "De Pijp", "area": "South"},
            {"name": "Oud-West", "area": "West"},
            {"name": "Centrum", "area": "Central"},
        ],
        "paris": [
            {"name": "Le Marais", "area": "Central"},
            {"name": "Montmartre", "area": "North"},
            {"name": "Saint-Germain", "area": "Left Bank"},
            {"name": "Bastille", "area": "East"},
        ],
        "vienna": [
            {"name": "Innere Stadt", "area": "Central"},
            {"name": "Neubau", "area": "Central"},
            {"name": "Josefstadt", "area": "Central"},
        ],
        "dublin": [
            {"name": "Temple Bar", "area": "Central"},
            {"name": "Ranelagh", "area": "South"},
            {"name": "Stoneybatter", "area": "North"},
        ],
        "atlanta": [
            {"name": "Midtown", "area": "Central"},
            {"name": "Buckhead", "area": "North"},
            {"name": "Decatur", "area": "East"},
            {"name": "Virginia-Highland", "area": "East"},
            {"name": "Inman Park", "area": "East"},
        ],
        "tampa": [
            {"name": "Downtown", "area": "Central"},
            {"name": "Hyde Park", "area": "South"},
            {"name": "Seminole Heights", "area": "North"},
            {"name": "South Tampa", "area": "South"},
        ],
    }
    return districts_by_city.get(key, districts_by_city.get("berlin", []))


def _mock_shortlist(city: str, max_results: int = 5) -> list[Neighborhood]:
    """Return mock neighborhoods when no API is available."""
    mock_db: dict[str, list[dict]] = {
        "berlin": [
            {"name": "Mitte", "area": "Central", "city": "Berlin", "score": 8.5, "highlights": ["Transit", "Culture"], "avg_rent_1bed_eur": 1200},
            {"name": "Kreuzberg", "area": "Central", "city": "Berlin", "score": 8.2, "highlights": ["Diverse", "Nightlife"], "avg_rent_1bed_eur": 1100},
            {"name": "Prenzlauer Berg", "area": "East", "city": "Berlin", "score": 8.4, "highlights": ["Family-friendly", "Parks"], "avg_rent_1bed_eur": 1150},
            {"name": "Charlottenburg", "area": "West", "city": "Berlin", "score": 8.0, "highlights": ["Quiet", "Shopping"], "avg_rent_1bed_eur": 1250},
            {"name": "Friedrichshain", "area": "East", "city": "Berlin", "score": 8.1, "highlights": ["Young", "Restaurants"], "avg_rent_1bed_eur": 1050},
        ],
        "munich": [
            {"name": "Schwabing", "area": "North", "city": "Munich", "score": 8.6, "highlights": ["Universities", "Cafes"], "avg_rent_1bed_eur": 1400},
            {"name": "Maxvorstadt", "area": "Central", "city": "Munich", "score": 8.4, "highlights": ["Museums", "Transit"], "avg_rent_1bed_eur": 1350},
            {"name": "Glockenbach", "area": "Central", "city": "Munich", "score": 8.2, "highlights": ["Diverse", "Nightlife"], "avg_rent_1bed_eur": 1300},
            {"name": "Haidhausen", "area": "East", "city": "Munich", "score": 8.3, "highlights": ["Parks", "Family"], "avg_rent_1bed_eur": 1380},
            {"name": "Sendling", "area": "South", "city": "Munich", "score": 7.9, "highlights": ["Affordable", "Transit"], "avg_rent_1bed_eur": 1180},
        ],
        "london": [
            {"name": "Shoreditch", "area": "East", "city": "London", "score": 8.3, "highlights": ["Tech", "Nightlife"], "avg_rent_1bed_eur": 1800},
            {"name": "Camden", "area": "North", "city": "London", "score": 8.1, "highlights": ["Culture", "Markets"], "avg_rent_1bed_eur": 1700},
            {"name": "Clapham", "area": "South", "city": "London", "score": 8.0, "highlights": ["Young professionals", "Parks"], "avg_rent_1bed_eur": 1600},
            {"name": "Islington", "area": "North", "city": "London", "score": 8.2, "highlights": ["Transit", "Dining"], "avg_rent_1bed_eur": 1750},
            {"name": "Bermondsey", "area": "South", "city": "London", "score": 7.8, "highlights": ["Riverside", "Quieter"], "avg_rent_1bed_eur": 1550},
        ],
        "atlanta": [
            {"name": "Midtown", "area": "Central", "city": "Atlanta", "score": 8.2, "highlights": ["Transit", "Dining"], "avg_rent_1bed_eur": 1800},
            {"name": "Buckhead", "area": "North", "city": "Atlanta", "score": 8.0, "highlights": ["Quiet", "Shopping"], "avg_rent_1bed_eur": 1900},
            {"name": "Decatur", "area": "East", "city": "Atlanta", "score": 8.3, "highlights": ["Family-friendly", "Parks"], "avg_rent_1bed_eur": 1600},
            {"name": "Virginia-Highland", "area": "East", "city": "Atlanta", "score": 8.1, "highlights": ["Walkable", "Restaurants"], "avg_rent_1bed_eur": 1700},
            {"name": "Inman Park", "area": "East", "city": "Atlanta", "score": 8.0, "highlights": ["Young", "Transit"], "avg_rent_1bed_eur": 1750},
        ],
        "tampa": [
            {"name": "Downtown", "area": "Central", "city": "Tampa", "score": 7.9, "highlights": ["Transit", "Work"], "avg_rent_1bed_eur": 1600},
            {"name": "Hyde Park", "area": "South", "city": "Tampa", "score": 8.2, "highlights": ["Walkable", "Dining"], "avg_rent_1bed_eur": 1700},
            {"name": "Seminole Heights", "area": "North", "city": "Tampa", "score": 7.8, "highlights": ["Affordable", "Arts"], "avg_rent_1bed_eur": 1400},
            {"name": "South Tampa", "area": "South", "city": "Tampa", "score": 8.1, "highlights": ["Family", "Parks"], "avg_rent_1bed_eur": 1650},
        ],
    }
    key = city.lower().strip() if city else "berlin"
    raw = mock_db.get(key, mock_db.get("berlin", list(mock_db.values())[0]))[:max_results]
    return [
        Neighborhood(
            name=r["name"],
            area=r["area"],
            city=r["city"],
            score=r["score"],
            highlights=r["highlights"],
            avg_rent_1bed_eur=r.get("avg_rent_1bed_eur"),
        )
        for r in raw
    ]


def _fetch_from_api(base_url: str, city: str, max_results: int) -> list[Neighborhood]:
    """Call external neighborhood API. Expects GET .../neighborhoods?city=...&limit=..."""
    url = base_url.rstrip("/") + "/neighborhoods"
    params = {"city": city, "limit": max_results}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []
    items = data if isinstance(data, list) else data.get("neighborhoods", data.get("results", []))
    out: list[Neighborhood] = []
    for r in items:
        if isinstance(r, dict):
            out.append(
                Neighborhood(
                    name=str(r.get("name", r.get("area", ""))),
                    area=str(r.get("area", r.get("region", ""))),
                    city=str(r.get("city", city)),
                    score=float(r.get("score", r.get("rating", 0))),
                    highlights=list(r.get("highlights", r.get("tags", []))),
                    avg_rent_1bed_eur=int(r["avg_rent_1bed_eur"]) if r.get("avg_rent_1bed_eur") is not None else None,
                )
            )
    return out[:max_results]


def shortlist_neighborhoods(
    city: str,
    max_results: int = 5,
    **kwargs: object,
) -> list[Neighborhood]:
    """
    Shortlist neighborhoods for a city from geolocation/APIs (no hardcoded lists by default).
    - If NEIGHBORHOOD_API_URL is set: use that custom API.
    - Else: use OpenStreetMap (Nominatim + Overpass) for real neighborhood/suburb data.
    - If OSM returns nothing: try Teleport API for city overview + district names.
    - If both fail: use built-in mock data as last resort.
    """
    api_url = os.environ.get("NEIGHBORHOOD_API_URL", "").strip()
    if api_url:
        return _fetch_from_api(api_url, city or "Berlin", max_results)
    city_val = city or "Berlin"
    osm_result = _fetch_osm_neighborhoods(city_val, city_val, max_results)
    if osm_result:
        return osm_result
    teleport_result = _fetch_teleport(city_val, city_val, max_results)
    if teleport_result:
        return teleport_result
    return _mock_shortlist(city_val, max_results)
