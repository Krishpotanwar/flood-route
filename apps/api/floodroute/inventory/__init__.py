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


def get_city_for_point(lat: float, lon: float) -> str | None:
    """Return city name whose bbox contains the point, else None."""
    for name, (w, s, e, n) in CITIES.items():
        if s <= lat <= n and w <= lon <= e:
            return name
    return None


def get_city_id_for_point(lat: float, lon: float) -> int | None:
    """Return city ID whose bbox contains the point, else None."""
    city_name = get_city_for_point(lat, lon)
    return CITY_IDS[city_name] if city_name is not None else None


def parse_bbox(bbox: str, max_deg: float | None = None) -> tuple[float, float, float, float]:
    """Parse and validate bounding box string 'min_lon,min_lat,max_lon,max_lat'."""
    try:
        parts = [float(x.strip()) for x in bbox.split(",")]
        if len(parts) != 4:
            raise ValueError
        min_lon, min_lat, max_lon, max_lat = parts
        if min_lon > max_lon or min_lat > max_lat:
            raise ValueError
        if not (
            -180.0 <= min_lon <= 180.0
            and -180.0 <= max_lon <= 180.0
            and -90.0 <= min_lat <= 90.0
            and -90.0 <= max_lat <= 90.0
        ):
            raise ValueError
    except (ValueError, AttributeError):
        raise ValueError("invalid bbox; expected min_lon,min_lat,max_lon,max_lat") from None

    if max_deg is not None and (max_lon - min_lon > max_deg or max_lat - min_lat > max_deg):
        raise ValueError(f"bbox wider than {max_deg} degrees; query smaller windows")

    return min_lon, min_lat, max_lon, max_lat

