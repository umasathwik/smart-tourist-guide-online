"""Smart Tourist Guide: Flask API + ML recommendations + OSM routing/POIs."""
from __future__ import annotations

import math
import re
import threading
import time
from urllib.parse import quote, urlencode

import requests
from flask import Flask, jsonify, render_template, request

from ml_model import df as TOURIST_DF, MODEL_METRICS, recommend_for_city

app = Flask(__name__)

# Public OpenStreetMap services have usage limits. Cache results to reduce calls.
GEOCODE_CACHE: dict[str, dict] = {}
NEARBY_CACHE: dict[tuple, dict] = {}
IMAGE_CACHE: dict[str, str | None] = {}
CACHE_TTL_SECONDS = 60 * 60
CACHE_CREATED: dict[tuple, float] = {}
GEOCODE_LOCK = threading.Lock()
LAST_GEOCODE_REQUEST_AT = 0.0
USER_AGENT = "SmartTouristGuideEducationalProject/1.0 (student project)"

CITY_CENTERS = {
    "hyderabad": {"name": "Hyderabad", "lat": 17.3850, "lon": 78.4867},
    "vizag": {"name": "Vizag", "lat": 17.6868, "lon": 83.2185},
    "visakhapatnam": {"name": "Vizag", "lat": 17.6868, "lon": 83.2185},
    "chennai": {"name": "Chennai", "lat": 13.0827, "lon": 80.2707},
    "bengaluru": {"name": "Bengaluru", "lat": 12.9716, "lon": 77.5946},
    "bangalore": {"name": "Bengaluru", "lat": 12.9716, "lon": 77.5946},
    "delhi": {"name": "Delhi", "lat": 28.6139, "lon": 77.2090},
    "mumbai": {"name": "Mumbai", "lat": 19.0760, "lon": 72.8777},
}

# -------- General helpers --------
def cache_get(cache, key):
    created = CACHE_CREATED.get((id(cache), key), 0)
    if key in cache and time.time() - created < CACHE_TTL_SECONDS:
        return cache[key]
    return None


def cache_set(cache, key, value):
    cache[key] = value
    CACHE_CREATED[(id(cache), key)] = time.time()


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def known_city_from_text(*values):
    joined = " ".join(str(v or "") for v in values).casefold()
    if "visakhapatnam" in joined or "vizag" in joined:
        return "Vizag"
    if "hyderabad" in joined:
        return "Hyderabad"
    if "chennai" in joined:
        return "Chennai"
    if "bengaluru" in joined or "bangalore" in joined:
        return "Bengaluru"
    if "delhi" in joined or "new delhi" in joined:
        return "Delhi"
    if "mumbai" in joined or "bombay" in joined:
        return "Mumbai"
    return None


def resolve_location(raw_query: str) -> dict:
    """Resolve a user-entered place or @lat,lon string to coordinates."""
    query = (raw_query or "").strip()
    if not query:
        raise ValueError("Enter both the starting location and destination.")

    # Browser location button sends @latitude,longitude after explicit permission.
    coord_match = re.fullmatch(r"@?\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*", query)
    if coord_match:
        lat, lon = float(coord_match.group(1)), float(coord_match.group(2))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Those coordinates are outside valid latitude/longitude ranges.")
        return {"name": "Selected coordinates", "lat": lat, "lon": lon, "display_name": query}

    key = query.casefold()
    cached = cache_get(GEOCODE_CACHE, key)
    if cached:
        return cached

    # Known cities can resolve immediately without network calls.
    if key in CITY_CENTERS:
        city = CITY_CENTERS[key].copy()
        city["display_name"] = city["name"] + ", India"
        cache_set(GEOCODE_CACHE, key, city)
        return city

    # Use exact curated tourist-place coordinates if present.
    place_matches = TOURIST_DF[TOURIST_DF["Place"].str.casefold() == key]
    if not place_matches.empty:
        row = place_matches.iloc[0]
        result = {
            "name": str(row["Place"]),
            "lat": float(row["Latitude"]),
            "lon": float(row["Longitude"]),
            "display_name": f"{row['Place']}, {row['City']}, India",
        }
        cache_set(GEOCODE_CACHE, key, result)
        return result

    # Nominatim policy asks for no more than one request per second.
    global LAST_GEOCODE_REQUEST_AT
    with GEOCODE_LOCK:
        delay = 1.1 - (time.time() - LAST_GEOCODE_REQUEST_AT)
        if delay > 0:
            time.sleep(delay)
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "jsonv2", "limit": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=18,
        )
        LAST_GEOCODE_REQUEST_AT = time.time()

    response.raise_for_status()
    items = response.json()
    if not items:
        raise ValueError(f"Location not found: {query}. Try a city, landmark, or full address.")
    item = items[0]
    result = {
        "name": item.get("name") or query,
        "lat": float(item["lat"]),
        "lon": float(item["lon"]),
        "display_name": item.get("display_name", query),
    }
    cache_set(GEOCODE_CACHE, key, result)
    return result


def get_route(origin: dict, destination: dict) -> dict:
    """Return fastest driving route from OSRM, or a clearly labelled fallback line."""
    key = (round(origin["lat"], 5), round(origin["lon"], 5), round(destination["lat"], 5), round(destination["lon"], 5))
    cached = cache_get(NEARBY_CACHE, ("route", key))
    if cached:
        return cached

    air_distance = haversine_km(origin["lat"], origin["lon"], destination["lat"], destination["lon"])
    fallback = {
        "distance_km": air_distance * 1.25,
        "duration_minutes": None,
        "geometry": {"type": "LineString", "coordinates": [[origin["lon"], origin["lat"]], [destination["lon"], destination["lat"]]]},
        "source": "Estimated distance only; road routing service unavailable",
        "alternatives": [],
    }
    coords = f"{origin['lon']},{origin['lat']};{destination['lon']},{destination['lat']}"
    try:
        response = requests.get(
            f"https://router.project-osrm.org/route/v1/driving/{coords}",
            params={"overview": "full", "geometries": "geojson", "alternatives": "true"},
            headers={"User-Agent": USER_AGENT}, timeout=22,
        )
        response.raise_for_status()
        payload = response.json()
        routes = payload.get("routes", []) if payload.get("code") == "Ok" else []
        if routes:
            best = routes[0]
            result = {
                "distance_km": best["distance"] / 1000,
                "duration_minutes": best["duration"] / 60,
                "geometry": best.get("geometry"),
                "source": "OSRM fastest driving route (not live traffic)",
                "alternatives": [
                    {"distance_km": r["distance"] / 1000, "duration_minutes": r["duration"] / 60}
                    for r in routes[1:]
                ],
            }
            cache_set(NEARBY_CACHE, ("route", key), result)
            return result
    except requests.RequestException:
        pass
    cache_set(NEARBY_CACHE, ("route", key), fallback)
    return fallback


def transport_estimates(road_distance_km: float, air_distance_km: float, road_duration_minutes=None):
    rail_distance_km = air_distance_km * 1.20
    # These rates are demonstration assumptions, not live ticket prices.
    car_hours = road_duration_minutes / 60 if road_duration_minutes else road_distance_km / 45
    return [
        {"mode": "Bus", "distance_km": round(road_distance_km, 1), "time": f"about {max(1, round(road_distance_km / 40))} h", "low": max(50, round(road_distance_km * 1.5)), "high": max(100, round(road_distance_km * 3.5)), "unit": "per passenger, one way", "note": "Estimated road travel; operator fares may differ."},
        {"mode": "Car", "distance_km": round(road_distance_km, 1), "time": f"about {max(1, round(car_hours))} h", "low": max(100, round(road_distance_km * 8)), "high": max(200, round(road_distance_km * 14)), "unit": "per car, one way", "note": "Fuel/usage estimate; excludes tolls, parking and driver costs."},
        {"mode": "Train", "distance_km": round(rail_distance_km, 1), "time": f"roughly {max(1, round(rail_distance_km / 50))} h (very approximate)", "low": max(50, round(rail_distance_km * 0.6)), "high": max(150, round(rail_distance_km * 2.0)), "unit": "per passenger, one way", "note": "Rail distance and fare depend on the actual rail route and class."},
        {"mode": "Airplane", "distance_km": round(air_distance_km, 1), "time": f"flight time estimate {max(1, round(air_distance_km / 650, 1))} h + airport time", "low": max(2500, round(air_distance_km * 4)), "high": max(6000, round(air_distance_km * 10)), "unit": "per passenger, one way", "note": "Distance is straight-line; fare is a rough placeholder, not a live quote."},
    ]


def nearby_pois(lat: float, lon: float, radius: int = 2500) -> dict:
    key = (round(lat, 4), round(lon, 4), radius)
    cached = cache_get(NEARBY_CACHE, ("pois", key))
    if cached:
        return cached

    q = f"""[out:json][timeout:18];
(
  nwr(around:{radius},{lat},{lon})[\"tourism\"~\"^(hotel|guest_house|hostel|motel|attraction|museum|viewpoint|zoo|theme_park|aquarium|gallery)$\"];
  nwr(around:{radius},{lat},{lon})[\"amenity\"~\"^(restaurant|cafe|fast_food|food_court)$\"];
  nwr(around:{radius},{lat},{lon})[\"historic\"];
  nwr(around:{radius},{lat},{lon})[\"leisure\"=\"park\"];
);
out center tags 100;"""

    elements = []
    errors = []
    for endpoint in ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]:
        try:
            response = requests.post(
                endpoint,
                data={"data": q},
                headers={"User-Agent": USER_AGENT},
                timeout=24,
            )
            response.raise_for_status()
            elements = response.json().get("elements", [])
            break
        except requests.RequestException as exc:
            errors.append(str(exc))

    result = {"hotels": [], "food": [], "attractions": [], "source": "OpenStreetMap", "warning": None}
    if not elements and errors:
        result["warning"] = "Nearby-place data is temporarily unavailable from the public map service. Try again later."
        cache_set(NEARBY_CACHE, ("pois", key), result)
        return result

    seen = set()
    categories = {"hotels": [], "food": [], "attractions": []}
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:en")
        if not name:
            continue
        latlon = (el.get("lat"), el.get("lon"))
        if latlon[0] is None or latlon[1] is None:
            center = el.get("center", {})
            latlon = (center.get("lat"), center.get("lon"))
        if latlon[0] is None or latlon[1] is None:
            continue
        dedup = (str(name).casefold(), round(float(latlon[0]), 5), round(float(latlon[1]), 5))
        if dedup in seen:
            continue
        seen.add(dedup)
        dist = haversine_km(lat, lon, float(latlon[0]), float(latlon[1]))
        tourism = tags.get("tourism", "")
        amenity = tags.get("amenity", "")
        if tourism in {"hotel", "guest_house", "hostel", "motel"}:
            bucket = "hotels"
            kind = tourism.replace("_", " ").title()
        elif amenity in {"restaurant", "cafe", "fast_food", "food_court"}:
            bucket = "food"
            kind = amenity.replace("_", " ").title()
        elif tourism in {"attraction", "museum", "viewpoint", "zoo", "theme_park", "aquarium", "gallery"} or "historic" in tags or tags.get("leisure") == "park":
            bucket = "attractions"
            kind = tourism.replace("_", " ").title() if tourism else ("Park" if tags.get("leisure") == "park" else "Historic place")
        else:
            continue
        categories[bucket].append({
            "name": str(name), "kind": kind,
            "distance_km": round(dist, 2),
            "lat": float(latlon[0]), "lon": float(latlon[1]),
            "cuisine": tags.get("cuisine", ""),
            "website": tags.get("website", ""),
            "opening_hours": tags.get("opening_hours", ""),
            "stars": tags.get("stars", ""),
        })

    for bucket in categories:
        categories[bucket].sort(key=lambda item: item["distance_km"])
        result[bucket] = categories[bucket][:8]

    cache_set(NEARBY_CACHE, ("pois", key), result)
    return result


def wikipedia_thumbnail(place_name: str, city: str):
    key = f"{place_name}|{city}".casefold()
    if key in IMAGE_CACHE:
        return IMAGE_CACHE[key]
    title = f"{place_name} {city}"
    try:
        response = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "query", "format": "json", "generator": "search", "gsrsearch": title, "gsrnamespace": 0, "gsrlimit": 1, "prop": "pageimages", "piprop": "thumbnail", "pithumbsize": 480},
            headers={"User-Agent": USER_AGENT}, timeout=6,
        )
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", {})
        image_url = None
        for page in pages.values():
            thumbnail = page.get("thumbnail", {})
            candidate = thumbnail.get("source")
            if candidate and candidate.startswith("https://"):
                image_url = candidate
                break
        IMAGE_CACHE[key] = image_url
        return image_url
    except requests.RequestException:
        IMAGE_CACHE[key] = None
        return None


def google_maps_url(origin_text, destination_text, mode):
    # Convert the browser's @lat,lon marker into a coordinate string Google Maps accepts.
    origin_for_link = origin_text.strip()
    if origin_for_link.startswith("@"):
        origin_for_link = origin_for_link[1:]
    travelmode = "driving" if mode in {"Car", "Bus"} else "transit"
    if mode == "Airplane":
        return "https://www.google.com/travel/flights?q=" + quote(f"Flights from {origin_for_link} to {destination_text}")
    params = {"api": "1", "origin": origin_for_link, "destination": destination_text, "travelmode": travelmode}
    return "https://www.google.com/maps/dir/?" + urlencode(params)


def google_maps_search_url(name, destination):
    return "https://www.google.com/maps/search/?api=1&query=" + quote(f"{name}, near {destination}")


@app.get("/")
def home():
    return render_template("index.html", cities=["Hyderabad", "Vizag", "Chennai", "Bengaluru", "Delhi", "Mumbai"])


@app.get("/health")
def health():
    return jsonify({"status": "ok", "ml_models_loaded": True, "sample_places": int(len(TOURIST_DF))})


@app.get("/api/model-metrics")
def model_metrics():
    return jsonify(MODEL_METRICS)


@app.post("/api/plan")
def plan_trip():
    payload = request.get_json(silent=True) or request.form
    origin_text = str(payload.get("origin", "")).strip()
    destination_text = str(payload.get("destination", "")).strip()
    interest = str(payload.get("interest", "All")).strip() or "All"
    mode = str(payload.get("mode", "Compare all")).strip()
    try:
        budget = float(payload.get("budget", 1000))
        if budget < 0 or budget > 10000000:
            raise ValueError("Budget must be between 0 and 10,000,000 rupees.")
    except (TypeError, ValueError):
        return jsonify({"error": "Enter a valid non-negative budget."}), 400

    if not origin_text or not destination_text:
        return jsonify({"error": "Enter both From and To locations."}), 400

    try:
        origin = resolve_location(origin_text)
        destination = resolve_location(destination_text)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except requests.RequestException:
        return jsonify({"error": "The location search service is temporarily unavailable. Try again in a moment."}), 503

    road_route = get_route(origin, destination)
    air_distance_km = haversine_km(origin["lat"], origin["lon"], destination["lat"], destination["lon"])
    budgets = transport_estimates(road_route["distance_km"], air_distance_km, road_route.get("duration_minutes"))
    selected_budget = next((item for item in budgets if item["mode"] == mode), None)

    try:
        nearby = nearby_pois(destination["lat"], destination["lon"])
    except Exception:
        nearby = {"hotels": [], "food": [], "attractions": [], "source": "OpenStreetMap", "warning": "Nearby data unavailable."}

    matched_city = known_city_from_text(destination_text, destination.get("display_name", ""))
    ml_recommendations = recommend_for_city(matched_city, budget=budget, interest=interest, limit=6) if matched_city else []
    for rec in ml_recommendations:
        rec["image_url"] = wikipedia_thumbnail(rec["place"], rec["city"])
        rec["image_search_url"] = "https://www.google.com/search?tbm=isch&q=" + quote(f"{rec['place']} {rec['city']}")
        rec["maps_url"] = google_maps_search_url(rec["place"], destination_text)

    # Nearby OpenStreetMap objects can carry photo URLs; only expose HTTPS links.
    for bucket in ("hotels", "food", "attractions"):
        for item in nearby.get(bucket, []):
            item["maps_url"] = google_maps_search_url(item["name"], destination_text)

    response = {
        "origin": {"name": origin["name"], "display_name": origin.get("display_name", origin["name"]), "lat": origin["lat"], "lon": origin["lon"]},
        "destination": {"name": destination["name"], "display_name": destination.get("display_name", destination["name"]), "lat": destination["lat"], "lon": destination["lon"]},
        "route": road_route,
        "straight_line_distance_km": round(air_distance_km, 1),
        "transport_budgets": budgets,
        "selected_transport_budget": selected_budget,
        "directions_url": google_maps_url(origin_text, destination_text, mode if mode in {"Bus", "Car", "Train", "Airplane"} else "Car"),
        "nearby": nearby,
        "ml_recommendations": ml_recommendations,
        "ml_city_match": matched_city,
        "source_notes": [
            "Map data and nearby businesses: OpenStreetMap contributors.",
            "Driving route: OSRM demo service when available; it does not report live traffic.",
            "Transport costs and travel times are rough educational estimates, not live quotes.",
            "The ML model uses a small sample dataset; predicted ratings are demonstrations, not actual visitor reviews."
        ],
    }
    return jsonify(response)


if __name__ == "__main__":
    # For local development only. Production hosting uses Gunicorn.
    app.run(host="0.0.0.0", port=5000, debug=True)
