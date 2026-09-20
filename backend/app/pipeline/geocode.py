"""Geocoding stage: turn whatever the citizen gave us into a map pin.

Resolution order, best evidence first::

    1. GPS fix or a pin the citizen dropped   confidence 1.00
    2. GPS coordinates read from photo EXIF   confidence 0.90
    3. Nominatim forward geocode of the text  confidence 0.75
    4. A known Pune locality named in the text confidence 0.50
    5. Nothing -> the complaint goes to the review queue asking for a pin

Step 4 matters more than it looks: it is what keeps the product working when
the venue Wi-Fi dies. "Katraj dairy samor" still lands on the map.

Nominatim's usage policy is respected in code, not just in the README: a real
User-Agent, a hard one-request-per-second limiter shared across threads, results
biased to the Pune bounding box, and every lookup cached in SQLite so the same
query is never sent twice.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config.localities import LOCALITY_BY_NAME
from app.config.settings import settings
from app.models import GeocodeCache

logger = logging.getLogger(__name__)

#: Nominatim asks for at most 1 request per second from any one client.
_MIN_INTERVAL_SECONDS = 1.0
_rate_lock = threading.Lock()
_last_request_at = 0.0


@dataclass
class LocationResolution:
    """Where we think the complaint is, and how much we trust that."""

    lat: float | None = None
    lon: float | None = None
    source: str = "unknown"  # gps | pin | exif | nominatim | landmark | unknown
    confidence: float = 0.0
    display_name: str = ""
    note: str = ""

    @property
    def resolved(self) -> bool:
        return self.lat is not None and self.lon is not None


def _throttle() -> None:
    """Block until at least one second has passed since the last live request."""
    global _last_request_at
    with _rate_lock:
        elapsed = time.monotonic() - _last_request_at
        if elapsed < _MIN_INTERVAL_SECONDS:
            time.sleep(_MIN_INTERVAL_SECONDS - elapsed)
        _last_request_at = time.monotonic()


def _key(query: str) -> str:
    return hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()


def in_city(lat: float | None, lon: float | None) -> bool:
    """True when a coordinate falls inside the configured city bounding box."""
    if lat is None or lon is None:
        return False
    min_lon, min_lat, max_lon, max_lat = settings.city_bbox
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


# ---------------------------------------------------------------------------
#  Cache
# ---------------------------------------------------------------------------
def _cache_lookup(db: Session, query: str) -> GeocodeCache | None:
    try:
        row = db.execute(
            select(GeocodeCache).where(GeocodeCache.query_hash == _key(query))
        ).scalar_one_or_none()
    except SQLAlchemyError as exc:  # pragma: no cover
        logger.warning("Geocode cache read failed: %s", exc)
        return None
    if row is not None:
        row.hit_count += 1
    return row


def _cache_store(db: Session, query: str, resolution: LocationResolution) -> None:
    try:
        row = GeocodeCache(
            query_hash=_key(query),
            query=query[:500],
            lat=resolution.lat,
            lon=resolution.lon,
            display_name=resolution.display_name[:500],
            source=resolution.source,
            confidence=resolution.confidence,
            hit_count=0,
        )
        db.add(row)
        db.flush()
    except SQLAlchemyError as exc:  # pragma: no cover
        logger.warning("Geocode cache write failed: %s", exc)
        db.rollback()


# ---------------------------------------------------------------------------
#  Providers
# ---------------------------------------------------------------------------
def geocode_text(db: Session, query: str) -> LocationResolution:
    """Forward-geocode free text, cache-first.

    Never raises. A network failure, a timeout or a rate limit all return an
    unresolved result and the caller moves on to the next fallback.
    """
    query = (query or "").strip()
    if not query:
        return LocationResolution(note="no location text")

    cached = _cache_lookup(db, query)
    if cached is not None:
        if cached.lat is None:
            return LocationResolution(source="cache", note="previously unresolved (cached)")
        return LocationResolution(
            lat=cached.lat,
            lon=cached.lon,
            source=cached.source,
            confidence=cached.confidence,
            display_name=cached.display_name,
            note="from cache",
        )

    if not settings.geocoding_enabled:
        return LocationResolution(note="geocoding disabled")

    min_lon, min_lat, max_lon, max_lat = settings.city_bbox
    params = {
        "q": f"{query}, {settings.city_name}, India",
        "format": "jsonv2",
        "limit": "1",
        "viewbox": f"{min_lon},{max_lat},{max_lon},{min_lat}",
        "bounded": "1",
        "addressdetails": "0",
    }
    try:
        _throttle()
        response = httpx.get(
            f"{settings.nominatim_base_url}/search",
            params=params,
            headers={
                "User-Agent": settings.nominatim_user_agent,
                "Accept-Language": "en",
            },
            timeout=settings.nominatim_timeout_seconds,
        )
        response.raise_for_status()
        results = response.json()
    except Exception as exc:  # noqa: BLE001 - offline is an expected condition
        logger.info("Nominatim lookup failed for %r: %s", query[:60], exc)
        return LocationResolution(note=f"geocoder unavailable ({type(exc).__name__})")

    if not results:
        resolution = LocationResolution(source="nominatim", note="no match")
        _cache_store(db, query, resolution)
        return resolution

    top = results[0]
    try:
        lat, lon = float(top["lat"]), float(top["lon"])
    except (KeyError, TypeError, ValueError):
        return LocationResolution(note="malformed geocoder response")

    if not in_city(lat, lon):
        return LocationResolution(source="nominatim", note="match outside city bounds")

    resolution = LocationResolution(
        lat=lat,
        lon=lon,
        source="nominatim",
        confidence=0.75,
        display_name=str(top.get("display_name", ""))[:500],
    )
    _cache_store(db, query, resolution)
    return resolution


def locality_fallback(landmarks: list[str]) -> LocationResolution:
    """Map a recognised Pune locality name to its centroid. Works with no network."""
    for name in landmarks or []:
        locality = LOCALITY_BY_NAME.get(name)
        if locality is not None:
            return LocationResolution(
                lat=locality.lat,
                lon=locality.lon,
                source="landmark",
                confidence=0.50,
                display_name=f"{locality.name}, Pune (locality centre)",
                note="approximate - resolved from the locality name, not a precise address",
            )
    return LocationResolution(note="no known locality named")


# ---------------------------------------------------------------------------
#  Orchestration
# ---------------------------------------------------------------------------
def resolve_location(
    db: Session,
    *,
    lat: float | None = None,
    lon: float | None = None,
    coordinate_source: str = "gps",
    exif_lat: float | None = None,
    exif_lon: float | None = None,
    location_text: str = "",
    landmarks: list[str] | None = None,
) -> LocationResolution:
    """Apply the full resolution ladder and return the best available pin."""
    if lat is not None and lon is not None:
        if in_city(lat, lon):
            return LocationResolution(
                lat=lat,
                lon=lon,
                source=coordinate_source,
                confidence=1.0,
                display_name=location_text[:300],
            )
        logger.info("Supplied coordinate %.4f,%.4f is outside %s", lat, lon, settings.city_name)

    if exif_lat is not None and exif_lon is not None and in_city(exif_lat, exif_lon):
        return LocationResolution(
            lat=exif_lat,
            lon=exif_lon,
            source="exif",
            confidence=0.90,
            display_name=location_text[:300],
            note="read from the photo with the citizen's consent",
        )

    if location_text.strip():
        resolved = geocode_text(db, location_text)
        if resolved.resolved:
            if not resolved.display_name:
                resolved.display_name = location_text[:300]
            return resolved

    fallback = locality_fallback(landmarks or [])
    if fallback.resolved:
        return fallback

    return LocationResolution(
        source="unknown",
        note="Could not place this complaint on the map - an officer will be asked to add a pin",
    )


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS84 points.

    Shared by deduplication (the 150 m candidate radius) and the priority
    formula (the 200 m school/hospital bonus).
    """
    from math import asin, cos, radians, sin, sqrt

    earth_radius_m = 6371008.8
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = (
        sin(d_lat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    )
    return 2 * earth_radius_m * asin(sqrt(a))
