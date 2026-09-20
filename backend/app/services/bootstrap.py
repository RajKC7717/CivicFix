"""Load reference data (wards, POIs, default settings) into the database.

Idempotent: safe to call on every startup. Reference data comes from the files
in ``data/`` so that the database is always reproducible from the repository.
"""

from __future__ import annotations

import csv
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import DATA_DIR
from app.models import Poi, Setting, Ward

logger = logging.getLogger(__name__)

WARDS_GEOJSON = DATA_DIR / "wards.geojson"
POIS_CSV = DATA_DIR / "pois.csv"

DEFAULT_SETTINGS: dict[str, Any] = {
    # Officers can switch the equity boost off from the dashboard; the change is
    # written to the audit log.
    "equity_boost_enabled": True,
}


def load_wards(db: Session) -> int:
    """Upsert ward rows from the GeoJSON. Returns the number of wards present."""
    if not WARDS_GEOJSON.exists():
        logger.warning("%s missing - run scripts/build_wards.py", WARDS_GEOJSON)
        return 0
    try:
        payload = json.loads(WARDS_GEOJSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Could not parse ward GeoJSON: %s", exc)
        return 0

    existing = {w.code: w for w in db.execute(select(Ward)).scalars().all()}
    for feature in payload.get("features", []):
        properties = feature.get("properties", {}) or {}
        code = str(properties.get("code", "")).strip()
        if not code:
            continue
        ward = existing.get(code) or Ward(code=code)
        ward.name = str(properties.get("name", code))
        ward.zone = str(properties.get("zone", ""))
        ward.population = int(properties.get("population", 0) or 0)
        ward.area_sq_km = float(properties.get("area_sq_km", 0) or 0)
        ward.centroid_lat = float(properties.get("centroid_lat", 0) or 0)
        ward.centroid_lon = float(properties.get("centroid_lon", 0) or 0)
        if code not in existing:
            db.add(ward)
    db.flush()
    return len(db.execute(select(Ward)).scalars().all())


def load_pois(db: Session) -> int:
    """Replace the POI table from the CSV. Returns the row count."""
    if not POIS_CSV.exists():
        logger.warning("%s missing - run scripts/build_wards.py", POIS_CSV)
        return 0

    already = db.execute(select(Poi)).scalars().all()
    if already:
        return len(already)

    count = 0
    with POIS_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                db.add(
                    Poi(
                        name=row["name"],
                        kind=row["kind"],
                        lat=float(row["lat"]),
                        lon=float(row["lon"]),
                        ward_code=row.get("ward_code") or None,
                    )
                )
                count += 1
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping malformed POI row %s: %s", row, exc)
    db.flush()
    return count


def load_settings(db: Session) -> None:
    """Insert any missing default setting rows."""
    existing = {s.key for s in db.execute(select(Setting)).scalars().all()}
    for key, value in DEFAULT_SETTINGS.items():
        if key not in existing:
            db.add(Setting(key=key, value=value, updated_by="system"))
    db.flush()


def get_setting(db: Session, key: str, default: Any = None) -> Any:
    row = db.execute(select(Setting).where(Setting.key == key)).scalar_one_or_none()
    return row.value if row is not None else DEFAULT_SETTINGS.get(key, default)


def set_setting(db: Session, key: str, value: Any, *, actor: str = "system") -> None:
    row = db.execute(select(Setting).where(Setting.key == key)).scalar_one_or_none()
    if row is None:
        db.add(Setting(key=key, value=value, updated_by=actor))
    else:
        row.value = value
        row.updated_by = actor
    db.flush()


def ensure_reference_data(db: Session) -> dict[str, int]:
    """Load everything the pipeline needs before it can triage a complaint."""
    wards = load_wards(db)
    pois = load_pois(db)
    load_settings(db)
    db.commit()
    return {"wards": wards, "pois": pois}
