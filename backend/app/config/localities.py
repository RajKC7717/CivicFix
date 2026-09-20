"""Pune locality reference data.

These twelve localities are real places with real approximate centroids. They
are the single source of truth for three things:

* the seed points of the synthetic ward tessellation (``scripts/build_wards.py``),
* the offline geocoding fallback, so a complaint that names "Katraj" still gets
  a map pin when Nominatim is unreachable,
* the landmark vocabulary used by the synthetic data generator.

The ward *boundaries* derived from these points are synthetic (PLAN.md D5); the
points themselves are not.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Locality:
    name: str
    ward_code: str
    lat: float
    lon: float
    zone: str
    population: int


PUNE_LOCALITIES: tuple[Locality, ...] = (
    Locality("Shivajinagar", "W01", 18.5308, 73.8478, "Central", 198000),
    Locality("Swargate", "W02", 18.5018, 73.8586, "Central", 176000),
    Locality("Kothrud", "W03", 18.5074, 73.8077, "West", 312000),
    Locality("Warje", "W04", 18.4823, 73.8069, "West", 164000),
    Locality("Katraj", "W05", 18.4575, 73.8677, "South", 228000),
    Locality("Kondhwa", "W06", 18.4649, 73.8918, "South", 289000),
    Locality("Hadapsar", "W07", 18.5089, 73.9260, "East", 341000),
    Locality("Yerawada", "W08", 18.5510, 73.8800, "East", 207000),
    Locality("Aundh", "W09", 18.5590, 73.8074, "North-West", 152000),
    Locality("Baner", "W10", 18.5590, 73.7868, "North-West", 186000),
    Locality("Wakad", "W11", 18.5975, 73.7898, "PCMC-fringe", 243000),
    Locality("Hinjewadi", "W12", 18.5912, 73.7389, "PCMC-fringe", 171000),
)

LOCALITY_BY_NAME: dict[str, Locality] = {loc.name: loc for loc in PUNE_LOCALITIES}
LOCALITY_BY_WARD: dict[str, Locality] = {loc.ward_code: loc for loc in PUNE_LOCALITIES}
LOCALITY_NAMES: tuple[str, ...] = tuple(loc.name for loc in PUNE_LOCALITIES)

#: Wards seeded with a deliberately worse service record so the equity audit has
#: something real to surface. Disclosed in docs/DISCLOSURES.md - this is a
#: property of the *synthetic data*, not a claim about these real places.
UNDERSERVED_WARD_CODES: tuple[str, ...] = ("W06", "W08")
