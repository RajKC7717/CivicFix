"""Ward assignment: point-in-polygon against the ward boundary GeoJSON.

The boundaries in ``data/wards.geojson`` are a Voronoi tessellation of twelve
real Pune locality centroids, clipped to the city bounding box (PLAN.md D5 and
docs/DISCLOSURES.md). They are *synthetic* and must not be read as the Pune
Municipal Corporation's real electoral wards. Drop a licensed real GeoJSON in
the same place with ``code``/``name`` properties and this module uses it
unchanged.

A useful property of a Voronoi tessellation: "which polygon contains this
point" and "which seed point is nearest" give the same answer. So if the
GeoJSON is missing or malformed, the nearest-centroid fallback is not an
approximation, it is exactly equivalent.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache

from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry
from shapely.prepared import PreparedGeometry, prep
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.localities import PUNE_LOCALITIES
from app.config.settings import DATA_DIR
from app.models import Poi, Ward
from app.pipeline.geocode import haversine_m

logger = logging.getLogger(__name__)

WARDS_GEOJSON = DATA_DIR / "wards.geojson"


@dataclass(frozen=True)
class WardHit:
    code: str
    name: str
    zone: str
    source: str = "polygon"


@dataclass
class _WardShape:
    code: str
    name: str
    zone: str
    geometry: BaseGeometry
    prepared: PreparedGeometry


@lru_cache(maxsize=1)
def load_ward_shapes() -> tuple[_WardShape, ...]:
    """Parse and prepare the ward polygons once per process."""
    if not WARDS_GEOJSON.exists():
        logger.warning("%s not found; ward assignment falls back to nearest centroid", WARDS_GEOJSON)
        return ()
    try:
        payload = json.loads(WARDS_GEOJSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read ward GeoJSON (%s); using nearest centroid", exc)
        return ()

    shapes: list[_WardShape] = []
    for feature in payload.get("features", []):
        properties = feature.get("properties", {}) or {}
        try:
            geometry = shape(feature["geometry"])
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Skipping malformed ward feature: %s", exc)
            continue
        shapes.append(
            _WardShape(
                code=str(properties.get("code", "")),
                name=str(properties.get("name", "")),
                zone=str(properties.get("zone", "")),
                geometry=geometry,
                prepared=prep(geometry),
            )
        )
    return tuple(shapes)


def nearest_ward(lat: float, lon: float) -> WardHit:
    """Nearest locality centroid. Always returns something."""
    best = min(PUNE_LOCALITIES, key=lambda loc: haversine_m(lat, lon, loc.lat, loc.lon))
    return WardHit(code=best.ward_code, name=best.name, zone=best.zone, source="nearest_centroid")


def ward_for_point(lat: float | None, lon: float | None) -> WardHit | None:
    """Return the ward containing this point, or ``None`` if there is no point."""
    if lat is None or lon is None:
        return None
    point = Point(lon, lat)
    for ward_shape in load_ward_shapes():
        if ward_shape.prepared.contains(point):
            return WardHit(code=ward_shape.code, name=ward_shape.name, zone=ward_shape.zone)
    # Outside every polygon (or no GeoJSON): snap to the nearest ward centre.
    return nearest_ward(lat, lon)


def ward_id_for_point(db: Session, lat: float | None, lon: float | None) -> int | None:
    """Resolve a coordinate to a ``wards.id`` foreign key."""
    hit = ward_for_point(lat, lon)
    if hit is None:
        return None
    row = db.execute(select(Ward).where(Ward.code == hit.code)).scalar_one_or_none()
    return row.id if row is not None else None


def nearby_pois(db: Session, lat: float | None, lon: float | None, radius_m: float) -> list[tuple[Poi, float]]:
    """Schools and hospitals within ``radius_m``, nearest first.

    A bounding-box pre-filter keeps this cheap: at Pune's latitude one degree of
    latitude is about 111 km, so we only ever measure the handful of POIs that
    could possibly qualify.
    """
    if lat is None or lon is None:
        return []
    degree_pad = (radius_m / 111_000.0) * 1.5
    candidates = db.execute(
        select(Poi).where(
            Poi.lat >= lat - degree_pad,
            Poi.lat <= lat + degree_pad,
            Poi.lon >= lon - degree_pad,
            Poi.lon <= lon + degree_pad,
        )
    ).scalars().all()

    hits: list[tuple[Poi, float]] = []
    for poi in candidates:
        distance = haversine_m(lat, lon, poi.lat, poi.lon)
        if distance <= radius_m:
            hits.append((poi, distance))
    hits.sort(key=lambda pair: pair[1])
    return hits


def reset_cache() -> None:
    """Test hook: force the GeoJSON to be re-read."""
    load_ward_shapes.cache_clear()
