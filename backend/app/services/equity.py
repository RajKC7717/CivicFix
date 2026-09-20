"""Equity audit: is the city serving every ward and every language equally?

This is the SDG-16 half of NagarNetra. A grievance system that merely routes
complaints faster can still be quietly unfair - the wards that complain in
English get fixed first, and nobody has the number to prove it.

Two parities are measured:

* **Ward parity** - median time-to-resolve and SLA breach rate per ward against
  the city median. A ward is flagged when it is materially worse on either.
* **Language parity** - the same, split by the language the citizen wrote in,
  plus how often officers had to correct the AI for each language. If the
  classifier is worse in Marathi than in English, that is a fairness defect and
  it belongs on screen, not in a footnote.

A flag is never automatic punishment. It appears on the dashboard, and it
optionally adds a small, visible, switchable boost in the priority formula.

Small samples are excluded on purpose (``min_resolved_sample``): declaring a
ward "neglected" on the strength of two complaints would be its own injustice.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.categories import LANGUAGE_LABELS
from app.config.policy import priority_config
from app.models import AuditLog, Issue, Report, Ward

#: Recomputing on every complaint submission would be wasteful; the numbers move
#: on a scale of hours, not milliseconds.
_CACHE_TTL_SECONDS = 30.0
_cache: tuple[float, set[str]] | None = None


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _resolution_hours(issue: Issue) -> float | None:
    resolved_at = _aware(issue.resolved_at)
    created_at = _aware(issue.created_at)
    if resolved_at is None or created_at is None:
        return None
    return max(0.0, (resolved_at - created_at).total_seconds() / 3600.0)


@dataclass
class GroupEquity:
    """Service quality for one ward or one language."""

    key: str
    label: str
    total_issues: int = 0
    resolved_count: int = 0
    open_count: int = 0
    median_resolution_hours: float | None = None
    breach_rate: float = 0.0
    flagged: bool = False
    reasons: list[str] = field(default_factory=list)
    #: Ratio of this group's median resolution time to the city median.
    ratio_to_city: float | None = None

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "total_issues": self.total_issues,
            "resolved_count": self.resolved_count,
            "open_count": self.open_count,
            "median_resolution_hours": (
                round(self.median_resolution_hours, 1)
                if self.median_resolution_hours is not None
                else None
            ),
            "breach_rate": round(self.breach_rate, 4),
            "flagged": self.flagged,
            "reasons": self.reasons,
            "ratio_to_city": round(self.ratio_to_city, 2) if self.ratio_to_city else None,
        }


@dataclass
class EquityReport:
    city_median_resolution_hours: float | None
    city_breach_rate: float
    wards: list[GroupEquity]
    languages: list[GroupEquity]
    language_accuracy: list[dict]
    thresholds: dict
    flagged_ward_codes: list[str]

    def as_dict(self) -> dict:
        return {
            "city_median_resolution_hours": (
                round(self.city_median_resolution_hours, 1)
                if self.city_median_resolution_hours is not None
                else None
            ),
            "city_breach_rate": round(self.city_breach_rate, 4),
            "wards": [w.as_dict() for w in self.wards],
            "languages": [lang.as_dict() for lang in self.languages],
            "language_accuracy": self.language_accuracy,
            "thresholds": self.thresholds,
            "flagged_ward_codes": self.flagged_ward_codes,
        }


def _evaluate_group(
    group: GroupEquity,
    durations: list[float],
    city_median: float | None,
    city_breach_rate: float,
    config: dict,
) -> None:
    """Fill in medians and decide whether this group is flagged."""
    minimum_sample = int(config.get("min_resolved_sample", 3))
    ratio_threshold = float(config.get("underserved_ratio", 1.5))
    breach_margin = float(config.get("underserved_breach_margin", 0.15))

    if durations:
        group.median_resolution_hours = statistics.median(durations)

    if (
        group.median_resolution_hours is not None
        and city_median
        and len(durations) >= minimum_sample
    ):
        group.ratio_to_city = group.median_resolution_hours / city_median
        if group.ratio_to_city >= ratio_threshold:
            group.flagged = True
            group.reasons.append(
                f"Median fix time {group.median_resolution_hours:.0f} h is "
                f"{group.ratio_to_city:.1f}x the city median of {city_median:.0f} h"
            )

    if group.total_issues >= minimum_sample and group.breach_rate >= city_breach_rate + breach_margin:
        group.flagged = True
        group.reasons.append(
            f"SLA breach rate {group.breach_rate:.0%} vs {city_breach_rate:.0%} city-wide"
        )


def _language_accuracy(db: Session) -> list[dict]:
    """Live proxy for classification accuracy: how often officers corrected us.

    This is not a held-out benchmark (that lives in docs/EVALUATION.md and on the
    AI Health page). It is the number that matters operationally: per language,
    what share of issues did a human have to re-categorise?
    """
    overridden_issue_ids = {
        row[0]
        for row in db.execute(
            select(AuditLog.entity_id).where(
                AuditLog.action == "override_category",
                AuditLog.entity_type == "issue",
            )
        ).all()
        if row[0]
    }

    totals: dict[str, int] = {}
    corrected: dict[str, int] = {}
    rows = db.execute(select(Report.language, Report.issue_id, Report.ai_source)).all()
    for language, issue_id, ai_source in rows:
        if ai_source == "officer":
            continue
        key = language or "unknown"
        totals[key] = totals.get(key, 0) + 1
        if issue_id is not None and str(issue_id) in overridden_issue_ids:
            corrected[key] = corrected.get(key, 0) + 1

    output: list[dict] = []
    for key, total in sorted(totals.items(), key=lambda pair: -pair[1]):
        wrong = corrected.get(key, 0)
        output.append(
            {
                "language": key,
                "label": LANGUAGE_LABELS.get(key, key),
                "reports": total,
                "officer_corrections": wrong,
                "agreement_rate": round(1.0 - (wrong / total), 4) if total else None,
            }
        )
    return output


def build_equity_report(db: Session) -> EquityReport:
    """Compute the full ward and language equity picture."""
    config = priority_config()["equity"]

    issues = list(db.execute(select(Issue)).scalars().all())
    wards = {w.id: w for w in db.execute(select(Ward)).scalars().all()}

    all_durations = [d for d in (_resolution_hours(i) for i in issues) if d is not None]
    city_median = statistics.median(all_durations) if all_durations else None
    city_breach_rate = (
        sum(1 for i in issues if i.sla_breached) / len(issues) if issues else 0.0
    )

    # ---- per ward ----
    ward_groups: dict[str, GroupEquity] = {}
    ward_durations: dict[str, list[float]] = {}
    for ward in wards.values():
        ward_groups[ward.code] = GroupEquity(key=ward.code, label=ward.name)
        ward_durations[ward.code] = []

    for issue in issues:
        ward = wards.get(issue.ward_id) if issue.ward_id else None
        if ward is None:
            continue
        group = ward_groups[ward.code]
        group.total_issues += 1
        if issue.resolved_at is not None:
            group.resolved_count += 1
            duration = _resolution_hours(issue)
            if duration is not None:
                ward_durations[ward.code].append(duration)
        else:
            group.open_count += 1
        if issue.sla_breached:
            group.breach_rate += 1

    for code, group in ward_groups.items():
        group.breach_rate = group.breach_rate / group.total_issues if group.total_issues else 0.0
        _evaluate_group(group, ward_durations[code], city_median, city_breach_rate, config)

    # ---- per language ----
    language_groups: dict[str, GroupEquity] = {}
    language_durations: dict[str, list[float]] = {}
    report_rows = db.execute(select(Report.language, Report.issue_id)).all()
    issue_by_id = {issue.id: issue for issue in issues}
    seen_pairs: set[tuple[str, int]] = set()

    for language, issue_id in report_rows:
        key = language or "unknown"
        if issue_id is None:
            continue
        if (key, issue_id) in seen_pairs:
            continue
        seen_pairs.add((key, issue_id))
        issue = issue_by_id.get(issue_id)
        if issue is None:
            continue
        group = language_groups.setdefault(
            key, GroupEquity(key=key, label=LANGUAGE_LABELS.get(key, key))
        )
        language_durations.setdefault(key, [])
        group.total_issues += 1
        if issue.resolved_at is not None:
            group.resolved_count += 1
            duration = _resolution_hours(issue)
            if duration is not None:
                language_durations[key].append(duration)
        else:
            group.open_count += 1
        if issue.sla_breached:
            group.breach_rate += 1

    for key, group in language_groups.items():
        group.breach_rate = group.breach_rate / group.total_issues if group.total_issues else 0.0
        _evaluate_group(group, language_durations[key], city_median, city_breach_rate, config)

    ward_list = sorted(
        ward_groups.values(),
        key=lambda g: (not g.flagged, -(g.median_resolution_hours or 0)),
    )
    language_list = sorted(language_groups.values(), key=lambda g: -g.total_issues)

    return EquityReport(
        city_median_resolution_hours=city_median,
        city_breach_rate=city_breach_rate,
        wards=ward_list,
        languages=language_list,
        language_accuracy=_language_accuracy(db),
        thresholds={
            "underserved_ratio": config.get("underserved_ratio"),
            "underserved_breach_margin": config.get("underserved_breach_margin"),
            "min_resolved_sample": config.get("min_resolved_sample"),
            "equity_points": config.get("points"),
        },
        flagged_ward_codes=[g.key for g in ward_list if g.flagged],
    )


def underserved_ward_codes(db: Session, *, use_cache: bool = True) -> set[str]:
    """Ward codes currently flagged by the audit, cached briefly.

    Called on every complaint submission by the priority engine, so it must be
    cheap; the underlying numbers change on the scale of hours.
    """
    global _cache
    now = time.monotonic()
    if use_cache and _cache is not None and (now - _cache[0]) < _CACHE_TTL_SECONDS:
        return _cache[1]
    codes = set(build_equity_report(db).flagged_ward_codes)
    _cache = (now, codes)
    return codes


def invalidate_cache() -> None:
    """Drop the cached flag set (after a reseed or a bulk status change)."""
    global _cache
    _cache = None
