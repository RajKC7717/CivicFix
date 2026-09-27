"""Service-level agreement: how long the city has promised to take.

Hours come from ``priority_config.yaml`` per category, and a hazard can only
ever *shorten* the deadline, never lengthen it. A live wire is four hours
whether it was filed as a streetlight problem or an electrical one.

The SLA clock starts when the citizen submits, not when an officer gets around
to looking. That is the point of a public accountability metric.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.config.policy import sla_config


@dataclass
class SlaAssignment:
    hours: int
    deadline: datetime
    reason: str


@dataclass
class SlaState:
    hours: int
    deadline: datetime | None
    breached: bool
    elapsed_hours: float
    remaining_hours: float
    fraction_used: float

    @property
    def label(self) -> str:
        if self.deadline is None:
            return "No deadline set"
        if self.breached:
            return f"Breached by {abs(self.remaining_hours) / 24:.1f} days"
        if self.remaining_hours < 24:
            return f"{self.remaining_hours:.0f} h left"
        return f"{self.remaining_hours / 24:.1f} days left"


def _aware(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def sla_hours_for(category: str, hazard_flags: list[str] | None = None) -> tuple[int, str]:
    """Resolve the promised turnaround for a category plus its hazards."""
    config = sla_config()
    base = int(config["by_category"].get(category, config["default_hours"]))
    reason = f"{base} h standard for this category"

    overrides = config.get("hazard_overrides", {}) or {}
    for flag in hazard_flags or []:
        override = overrides.get(flag)
        if override is not None and int(override) < base:
            base = int(override)
            reason = f"{base} h because of the '{flag.replace('_', ' ')}' hazard"
    return base, reason


def assign_sla(
    category: str,
    hazard_flags: list[str] | None = None,
    created_at: datetime | None = None,
) -> SlaAssignment:
    """Compute the deadline for a newly created or re-categorised issue."""
    hours, reason = sla_hours_for(category, hazard_flags)
    start = _aware(created_at)
    return SlaAssignment(hours=hours, deadline=start + timedelta(hours=hours), reason=reason)


def evaluate_sla(
    *,
    hours: int,
    created_at: datetime | None,
    deadline: datetime | None,
    resolved_at: datetime | None = None,
    now: datetime | None = None,
) -> SlaState:
    """Current SLA position. A resolved issue is judged at its resolution time."""
    now = _aware(now)
    start = _aware(created_at)
    reference = _aware(resolved_at) if resolved_at is not None else now
    deadline = _aware(deadline) if deadline is not None else start + timedelta(hours=hours)

    elapsed_hours = max(0.0, (reference - start).total_seconds() / 3600.0)
    remaining_hours = (deadline - reference).total_seconds() / 3600.0
    return SlaState(
        hours=hours,
        deadline=deadline,
        breached=remaining_hours < 0,
        elapsed_hours=elapsed_hours,
        remaining_hours=remaining_hours,
        fraction_used=(elapsed_hours / hours) if hours else 0.0,
    )


# ---------------------------------------------------------------------------
#  Acknowledgment window
# ---------------------------------------------------------------------------
def ack_hours_for(category: str, hazard_flags: list[str] | None = None) -> int:
    """Resolve the expected hours until an officer first reviews this issue."""
    from app.config.policy import policy_config

    config = policy_config()
    ack = config.get("ack_window", {})
    by_cat = ack.get("by_category", {})
    default = int(ack.get("default", 24))
    base = int(by_cat.get(category, default))

    overrides = ack.get("hazard_override", {}) or {}
    for flag in hazard_flags or []:
        override = overrides.get(flag)
        if override is not None and int(override) < base:
            base = int(override)
    return base


@dataclass
class AckAssignment:
    window_hours: int
    deadline: datetime


def assign_ack_window(
    category: str,
    hazard_flags: list[str] | None = None,
    created_at: datetime | None = None,
) -> AckAssignment:
    """Compute the acknowledgment deadline for a new issue."""
    hours = ack_hours_for(category, hazard_flags)
    start = _aware(created_at)
    return AckAssignment(window_hours=hours, deadline=start + timedelta(hours=hours))
