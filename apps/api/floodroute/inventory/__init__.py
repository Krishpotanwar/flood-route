from __future__ import annotations

# west, south, east, north (degrees). Margin around the municipal limits; also the geocoding box.
CITIES: dict[str, tuple[float, float, float, float]] = {
    "bengaluru": (77.40, 12.80, 77.85, 13.20),
    "chennai": (80.05, 12.85, 80.35, 13.25),
    "mumbai": (72.75, 18.88, 73.05, 19.30),
    "gurugram": (76.85, 28.32, 77.15, 28.56),
}

CITY_IDS: dict[str, int] = {
    "bengaluru": 1,
    "chennai": 2,
    "mumbai": 3,
    "gurugram": 4,
}


def get_city_id(city_name: str) -> int:
    norm = city_name.strip().lower()
    if norm not in CITY_IDS:
        raise KeyError(f"Unknown city '{city_name}'. Supported cities: {list(CITY_IDS.keys())}")
    return CITY_IDS[norm]

