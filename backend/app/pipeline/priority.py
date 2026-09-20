"""Explainable priority scoring.

The AI never produces the priority number. It extracts *features* - what kind of
problem this is, how severe it looks, which hazards are named. The number is
then computed by the plain weighted sum declared in ``priority_config.yaml``.

That split is the whole point. An officer who disagrees with a score can read
the six lines of arithmetic that produced it, see which input they dispute, and
correct that input. A model that emitted "87" could only be argued with.

Every component carries a ``source`` so the dashboard can colour-code where each
point came from: the AI's reading, the citizens who reported it, verified map
data, or the city's own written policy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from app.config.categories import HAZARD_BY_KEY
from app.config.policy import bands_config, priority_config
from app.models import Issue
from app.pipeline.ward import nearby_pois

#: Where a component's evidence came from - shown as a chip in the breakdown UI.
SOURCE_AI = "ai"
SOURCE_CITIZENS = "citizens"
SOURCE_MAP = "map"
SOURCE_POLICY = "policy"
SOURCE_EQUITY = "equity"

BAND_LABELS: dict[str, str] = {
    "P1": "Critical",
    "P2": "High",
    "P3": "Medium",
    "P4": "Low",
}

#: A hazard flag already charged for proximity makes the map-derived bonus
#: redundant: a complaint must not be charged twice for the same school.
_HAZARD_FOR_POI_KIND = {"school": "near_school", "hospital": "near_hospital"}


@dataclass
class ScoreComponent:
    """One line of the priority arithmetic."""

    key: str
    label: str
    points: float
    detail: str
    source: str

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "points": round(self.points, 1),
            "detail": self.detail,
            "source": self.source,
        }


@dataclass
class PriorityResult:
    score: float
    band: str
    components: list[ScoreComponent] = field(default_factory=list)
    equity_applied: bool = False

    @property
    def band_label(self) -> str:
        return BAND_LABELS.get(self.band, self.band)

    @property
    def headline(self) -> str:
        """One-line human summary, e.g. the example in the PS-18 brief."""
        parts = [f"{c.label} (+{c.points:.0f})" for c in self.components if c.points > 0]
        return " · ".join(parts)

    def as_dict(self) -> list[dict]:
        return [c.as_dict() for c in self.components]


def band_for_score(score: float) -> str:
    """Map a 0-100 score onto P1..P4 using the configured cut-offs."""
    bands = bands_config()
    for band in ("P1", "P2", "P3"):
        if score >= float(bands[band]):
            return band
    return "P4"


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def compute_priority(
    db: Session,
    issue: Issue,
    *,
    now: datetime | None = None,
    underserved_wards: Iterable[str] = (),
    equity_enabled: bool | None = None,
) -> PriorityResult:
    """Score one issue and return the full arithmetic behind the number."""
    config = priority_config()
    now = now or datetime.now(timezone.utc)
    components: list[ScoreComponent] = []

    # ---- 1. Severity -----------------------------------------------------
    severity = max(1, min(5, int(issue.severity or 3)))
    severity_points = min(
        float(config["severity"]["max_points"]),
        severity * float(config["severity"]["points_per_level"]),
    )
    components.append(
        ScoreComponent(
            key="severity",
            label=f"Severity {severity}/5",
            points=severity_points,
            detail=f"{severity} x {config['severity']['points_per_level']} points per level",
            source=SOURCE_AI,
        )
    )

    # ---- 2. Hazard flags -------------------------------------------------
    hazard_points_map = config["hazards"]["points"]
    hazard_total = 0.0
    hazard_flags = list(issue.hazard_flags or [])
    for flag in hazard_flags:
        points = float(hazard_points_map.get(flag, 0))
        if points <= 0:
            continue
        remaining = float(config["hazards"]["max_points"]) - hazard_total
        if remaining <= 0:
            break
        awarded = min(points, remaining)
        hazard_total += awarded
        label = HAZARD_BY_KEY[flag].label_en if flag in HAZARD_BY_KEY else flag
        components.append(
            ScoreComponent(
                key=f"hazard:{flag}",
                label=label,
                points=awarded,
                detail=f"hazard weight {points:g}"
                + (" (capped)" if awarded < points else ""),
                source=SOURCE_AI,
            )
        )

    # ---- 3. How many citizens reported it --------------------------------
    report_count = max(1, int(issue.report_count or 1))
    cluster_points = min(
        float(config["cluster"]["max_points"]),
        float(config["cluster"]["weight"]) * math.log10(1 + report_count),
    )
    components.append(
        ScoreComponent(
            key="cluster",
            label=f"{report_count} report{'s' if report_count != 1 else ''}",
            points=cluster_points,
            detail=f"{config['cluster']['weight']} x log10(1 + {report_count}), log-scaled so "
            "one street cannot be brigaded to the top",
            source=SOURCE_CITIZENS,
        )
    )

    # ---- 4. SLA pressure -------------------------------------------------
    created_at = _aware(issue.created_at) or now
    sla_hours = max(1, int(issue.sla_hours or 96))
    elapsed_hours = max(0.0, (now - created_at).total_seconds() / 3600.0)
    fraction = min(1.0, elapsed_hours / sla_hours)
    sla_points = float(config["sla_pressure"]["weight"]) * fraction
    breached = elapsed_hours > sla_hours and issue.resolved_at is None
    if breached:
        sla_points += float(config["sla_pressure"]["breach_bonus"])
        detail = f"SLA of {sla_hours} h breached {elapsed_hours - sla_hours:.0f} h ago"
        label = "SLA breached"
    else:
        remaining_hours = max(0.0, sla_hours - elapsed_hours)
        detail = f"{elapsed_hours:.0f} h of {sla_hours} h elapsed"
        label = (
            f"{remaining_hours / 24:.0f} days to SLA breach"
            if remaining_hours >= 24
            else f"{remaining_hours:.0f} h to SLA breach"
        )
    components.append(
        ScoreComponent(
            key="sla_pressure",
            label=label,
            points=sla_points,
            detail=detail,
            source=SOURCE_POLICY,
        )
    )

    # ---- 5. Vulnerable location (verified from map data) -----------------
    vulnerable_config = config["vulnerable_location"]
    radius_m = float(vulnerable_config["radius_m"])
    poi_total = 0.0
    if issue.lat is not None and issue.lon is not None:
        counted_kinds: set[str] = set()
        for poi, distance in nearby_pois(db, issue.lat, issue.lon, radius_m):
            kind = poi.kind
            if kind in counted_kinds:
                continue
            if _HAZARD_FOR_POI_KIND.get(kind) in hazard_flags:
                # Already charged as a hazard flag - do not double count.
                continue
            points = float(vulnerable_config["points"].get(kind, 0))
            if points <= 0:
                continue
            remaining = float(vulnerable_config["max_points"]) - poi_total
            if remaining <= 0:
                break
            awarded = min(points, remaining)
            poi_total += awarded
            counted_kinds.add(kind)
            components.append(
                ScoreComponent(
                    key=f"vulnerable:{kind}",
                    label=f"{poi.name} {distance:.0f} m away",
                    points=awarded,
                    detail=f"verified {kind} within {radius_m:.0f} m",
                    source=SOURCE_MAP,
                )
            )

    # ---- 6. Equity correction -------------------------------------------
    equity_config = config["equity"]
    equity_on = equity_config.get("enabled", True) if equity_enabled is None else equity_enabled
    equity_applied = False
    ward_code = issue.ward.code if issue.ward is not None else None
    if equity_on and ward_code and ward_code in set(underserved_wards):
        equity_applied = True
        components.append(
            ScoreComponent(
                key="equity",
                label="Under-served ward",
                points=float(equity_config["points"]),
                detail=(
                    f"Ward {ward_code} is currently flagged by the equity audit; "
                    "this adjustment is visible and can be switched off"
                ),
                source=SOURCE_EQUITY,
            )
        )

    raw_total = sum(component.points for component in components)
    score = max(0.0, min(float(config["max_score"]), raw_total))
    return PriorityResult(
        score=round(score, 1),
        band=band_for_score(score),
        components=components,
        equity_applied=equity_applied,
    )
