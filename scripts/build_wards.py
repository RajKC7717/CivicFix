"""Generate data/wards.geojson and data/pois.csv.

WARD BOUNDARIES ARE SYNTHETIC. No Pune ward GeoJSON with an unambiguous licence
was available, so we build a Voronoi tessellation of twelve *real* locality
centroids, clipped to the Pune bounding box. The result is gap-free,
non-overlapping and geographically plausible, and it is disclosed as synthetic
everywhere it is shown (docs/DISCLOSURES.md, PLAN.md D5).

To use real boundaries instead, replace data/wards.geojson with a licensed file
whose features carry ``code``, ``name`` and ``zone`` properties. Nothing else
needs to change.

The Voronoi cells are built by half-plane intersection rather than with
``scipy.spatial.Voronoi`` so that unbounded outer cells need no special casing:
every cell is clipped by the bounding box from the start.

Run:  python scripts/build_wards.py
"""

from __future__ import annotations

import csv
import json
import math
import random
import sys
from pathlib import Path

from shapely.geometry import Polygon, box, mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config.localities import PUNE_LOCALITIES  # noqa: E402
from app.config.settings import DATA_DIR, settings  # noqa: E402

SEED = 20260926
#: Far larger than the city bbox, so a half-plane always covers it completely.
_HUGE = 10.0


def clip_to_halfplane(polygon: Polygon, keep: tuple[float, float], drop: tuple[float, float]) -> Polygon:
    """Clip ``polygon`` to the side of the perpendicular bisector nearer ``keep``.

    Coordinates are (lon, lat) treated as planar. At city scale the distortion
    is far below the precision a ward boundary implies.
    """
    mid_x, mid_y = (keep[0] + drop[0]) / 2.0, (keep[1] + drop[1]) / 2.0
    dx, dy = drop[0] - keep[0], drop[1] - keep[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return polygon
    ux, uy = dx / length, dy / length          # unit vector keep -> drop
    px, py = -uy, ux                           # unit vector along the bisector

    a = (mid_x + px * _HUGE, mid_y + py * _HUGE)
    b = (mid_x - px * _HUGE, mid_y - py * _HUGE)
    c = (b[0] - ux * _HUGE, b[1] - uy * _HUGE)
    d = (a[0] - ux * _HUGE, a[1] - uy * _HUGE)
    result = polygon.intersection(Polygon([a, b, c, d]))
    return result if isinstance(result, Polygon) else polygon


def build_wards() -> dict:
    min_lon, min_lat, max_lon, max_lat = settings.city_bbox
    bounds = box(min_lon, min_lat, max_lon, max_lat)
    points = [(loc.lon, loc.lat) for loc in PUNE_LOCALITIES]

    features = []
    for index, locality in enumerate(PUNE_LOCALITIES):
        cell: Polygon = bounds
        for other_index, other in enumerate(points):
            if other_index != index:
                cell = clip_to_halfplane(cell, points[index], other)
        cell = cell.simplify(0.00015, preserve_topology=True)

        # Rough km^2: scale longitude by cos(latitude) before converting degrees.
        lat_km = 110.574
        lon_km = 111.320 * math.cos(math.radians(locality.lat))
        area_sq_km = round(cell.area * lat_km * lon_km, 2)

        features.append(
            {
                "type": "Feature",
                "properties": {
                    "code": locality.ward_code,
                    "name": locality.name,
                    "zone": locality.zone,
                    "population": locality.population,
                    "area_sq_km": area_sq_km,
                    "centroid_lat": locality.lat,
                    "centroid_lon": locality.lon,
                    "boundary_source": "synthetic-voronoi",
                },
                "geometry": mapping(cell),
            }
        )

    return {
        "type": "FeatureCollection",
        "name": "nagarnetra_synthetic_wards",
        "disclaimer": (
            "SYNTHETIC BOUNDARIES. Voronoi tessellation of real Pune locality "
            "centroids, clipped to the city bounding box. Not PMC electoral wards."
        ),
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features,
    }


#: Name templates per POI kind. Generic on purpose - these are fictional
#: facilities placed inside real localities, not real institutions.
_SCHOOL_TEMPLATES = (
    "{name} Municipal School",
    "{name} English Medium School",
    "Zilla Parishad School, {name}",
    "{name} Vidya Mandir",
)
_HOSPITAL_TEMPLATES = (
    "{name} Municipal Hospital",
    "{name} Primary Health Centre",
    "{name} Maternity Home",
)

#: The scripted demo depends on a school being inside the 200 m vulnerable-location
#: radius of the Katraj pothole, so that the "Near school (+10)" line appears in
#: the priority breakdown. This POI is placed deliberately, not randomly.
_DEMO_POIS = [
    {
        "name": "Katraj Dairy Road Municipal School",
        "kind": "school",
        "lat": 18.45862,
        "lon": 73.86790,
        "ward_code": "W05",
    },
]


def build_pois() -> list[dict]:
    rng = random.Random(SEED)
    rows: list[dict] = list(_DEMO_POIS)
    for locality in PUNE_LOCALITIES:
        for index in range(3):
            template = _SCHOOL_TEMPLATES[(index + hash(locality.name)) % len(_SCHOOL_TEMPLATES)]
            rows.append(
                {
                    "name": template.format(name=locality.name),
                    "kind": "school",
                    "lat": round(locality.lat + rng.uniform(-0.012, 0.012), 6),
                    "lon": round(locality.lon + rng.uniform(-0.012, 0.012), 6),
                    "ward_code": locality.ward_code,
                }
            )
        for index in range(2):
            template = _HOSPITAL_TEMPLATES[(index + hash(locality.zone)) % len(_HOSPITAL_TEMPLATES)]
            rows.append(
                {
                    "name": template.format(name=locality.name),
                    "kind": "hospital",
                    "lat": round(locality.lat + rng.uniform(-0.010, 0.010), 6),
                    "lon": round(locality.lon + rng.uniform(-0.010, 0.010), 6),
                    "ward_code": locality.ward_code,
                }
            )
    return rows


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    geojson = build_wards()
    target = DATA_DIR / "wards.geojson"
    target.write_text(json.dumps(geojson, indent=1), encoding="utf-8")
    total_area = sum(f["properties"]["area_sq_km"] for f in geojson["features"])
    print(f"wrote {target.relative_to(ROOT)}  ({len(geojson['features'])} wards, {total_area:.0f} km2)")

    pois = build_pois()
    poi_path = DATA_DIR / "pois.csv"
    with poi_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "kind", "lat", "lon", "ward_code"])
        writer.writeheader()
        writer.writerows(pois)
    schools = sum(1 for p in pois if p["kind"] == "school")
    print(f"wrote {poi_path.relative_to(ROOT)}  ({schools} schools, {len(pois) - schools} hospitals)")


if __name__ == "__main__":
    main()
