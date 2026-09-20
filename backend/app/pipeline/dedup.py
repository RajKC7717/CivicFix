"""Deduplication - "one issue, many voices".

The problem this solves is the reason PS-18 exists. Ten people report the same
open manhole in three languages; a conventional portal creates ten tickets, ten
work orders and ten separate SLA clocks, and the crew is dispatched ten times to
a hole that needed fixing once.

NagarNetra instead links those ten *reports* to one *issue*. The reports are
never merged away or deleted - each stays addressable by its own ticket code,
and the count of them is what drives the issue up the priority queue. A duplicate
is treated as corroborating evidence, not as spam.

Scoring
-------
A candidate must first pass three hard gates: same category, within
``radius_m``, reported within ``window_days``. Anything else is never compared,
which keeps false merges rare and the query cheap.

Surviving candidates are scored::

    similarity = w_text * cosine(summary_en) + w_distance * proximity + w_time * recency

against thresholds in ``priority_config.yaml``:

* ``>= auto_merge_threshold`` - joined automatically
* ``>= review_threshold``     - a human sees both reports side by side
* below                       - a new issue

Reports with no usable location skip the distance gate entirely and can only
ever reach *review*, never an automatic merge: without a pin we cannot tell one
pothole from the next street's pothole, and guessing would be worse than asking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.categories import OPEN_STATUSES
from app.config.policy import dedup_config
from app.models import Issue
from app.pipeline.embed import get_embedder, similarity
from app.pipeline.geocode import haversine_m

logger = logging.getLogger(__name__)

#: Text similarity required before a locationless report may even be reviewed.
LOCATIONLESS_TEXT_FLOOR = 0.85


@dataclass
class Candidate:
    """One open issue compared against the incoming report."""

    issue: Issue
    text_similarity: float
    distance_m: float | None
    distance_score: float
    hours_apart: float
    time_score: float
    score: float

    def as_dict(self) -> dict:
        return {
            "issue_id": self.issue.id,
            "issue_code": self.issue.issue_code,
            "title": self.issue.title,
            "report_count": self.issue.report_count,
            "score": round(self.score, 4),
            "text_similarity": round(self.text_similarity, 4),
            "distance_m": round(self.distance_m, 1) if self.distance_m is not None else None,
            "hours_apart": round(self.hours_apart, 1),
        }


@dataclass
class DedupDecision:
    """What to do with the incoming report, and why."""

    decision: str  # merge | review | new
    score: float = 0.0
    issue: Issue | None = None
    candidates: list[Candidate] = field(default_factory=list)
    explanation: str = ""

    def as_dict(self) -> dict:
        return {
            "decision": self.decision,
            "score": round(self.score, 4),
            "matched_issue_id": self.issue.id if self.issue else None,
            "explanation": self.explanation,
            "candidates": [c.as_dict() for c in self.candidates[:5]],
        }


def _aware(value: datetime | None) -> datetime:
    """SQLite hands back naive datetimes; treat them as UTC."""
    if value is None:
        return datetime.now(timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def find_candidates(
    db: Session,
    *,
    category: str,
    summary_en: str,
    lat: float | None,
    lon: float | None,
    created_at: datetime | None = None,
    exclude_issue_id: int | None = None,
) -> list[Candidate]:
    """Score every open issue that passes the category/distance/time gates."""
    config = dedup_config()
    radius_m = float(config["radius_m"])
    window_days = int(config["window_days"])
    weights = config["weights"]
    decay = float(config.get("distance_decay", 1.0))
    now = _aware(created_at)
    window_start = now - timedelta(days=window_days)

    query = select(Issue).where(
        Issue.category == category,
        Issue.status.in_(OPEN_STATUSES),
        Issue.merged_into_id.is_(None),
        Issue.created_at >= window_start.replace(tzinfo=None),
    )
    if exclude_issue_id is not None:
        query = query.where(Issue.id != exclude_issue_id)

    if lat is not None and lon is not None:
        # Cheap bounding-box pre-filter before the exact haversine.
        pad = (radius_m / 111_000.0) * 1.6
        query = query.where(
            Issue.lat.is_not(None),
            Issue.lon.is_not(None),
            Issue.lat >= lat - pad,
            Issue.lat <= lat + pad,
            Issue.lon >= lon - pad,
            Issue.lon <= lon + pad,
        )

    rows = list(db.execute(query.limit(200)).scalars().all())
    if not rows:
        return []

    geo_filtered: list[tuple[Issue, float | None]] = []
    for issue in rows:
        if lat is not None and lon is not None and issue.lat is not None and issue.lon is not None:
            distance = haversine_m(lat, lon, issue.lat, issue.lon)
            if distance > radius_m:
                continue
            geo_filtered.append((issue, distance))
        else:
            geo_filtered.append((issue, None))

    if not geo_filtered:
        return []

    max_candidates = int(config.get("max_candidates", 25))
    geo_filtered = geo_filtered[:max_candidates]

    embedder = get_embedder()
    texts = [summary_en or ""] + [(issue.title or "") for issue, _ in geo_filtered]
    vectors = embedder.encode(texts)
    text_scores = similarity(vectors[0], vectors[1:])[0]

    window_hours = window_days * 24.0
    candidates: list[Candidate] = []
    for index, (issue, distance) in enumerate(geo_filtered):
        text_similarity = float(text_scores[index])
        # Decay proximity gently inside the radius. The candidate has already
        # passed a hard distance gate, and two people pinning the same pothole
        # routinely differ by 50-100 m. See `distance_decay` in the policy file.
        distance_score = (
            1.0 - decay * min(1.0, distance / radius_m) if distance is not None else 0.0
        )
        hours_apart = abs((now - _aware(issue.created_at)).total_seconds()) / 3600.0
        time_score = max(0.0, 1.0 - min(1.0, hours_apart / window_hours))

        if distance is None:
            # No pin: renormalise over the two signals we actually have, so a
            # locationless report is not silently penalised into "new".
            usable = weights["text"] + weights["time"]
            score = (weights["text"] * text_similarity + weights["time"] * time_score) / usable
        else:
            score = (
                weights["text"] * text_similarity
                + weights["distance"] * distance_score
                + weights["time"] * time_score
            )

        candidates.append(
            Candidate(
                issue=issue,
                text_similarity=text_similarity,
                distance_m=distance,
                distance_score=distance_score,
                hours_apart=hours_apart,
                time_score=time_score,
                score=score,
            )
        )

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


def decide(
    db: Session,
    *,
    category: str,
    summary_en: str,
    lat: float | None,
    lon: float | None,
    created_at: datetime | None = None,
) -> DedupDecision:
    """Decide whether this report joins an existing issue, needs a human, or is new."""
    config = dedup_config()
    auto_threshold = float(config["auto_merge_threshold"])
    review_threshold = float(config["review_threshold"])

    if not (summary_en or "").strip():
        return DedupDecision(
            decision="new",
            explanation="No English summary could be produced, so no reliable comparison was possible.",
        )

    candidates = find_candidates(
        db,
        category=category,
        summary_en=summary_en,
        lat=lat,
        lon=lon,
        created_at=created_at,
    )
    if not candidates:
        return DedupDecision(
            decision="new",
            explanation="No open issue of this type was reported nearby in the last "
            f"{config['window_days']} days.",
        )

    best = candidates[0]
    has_location = best.distance_m is not None

    if not has_location:
        if best.text_similarity >= LOCATIONLESS_TEXT_FLOOR:
            return DedupDecision(
                decision="review",
                score=best.score,
                issue=best.issue,
                candidates=candidates,
                explanation=(
                    f"Wording closely matches {best.issue.issue_code} "
                    f"({best.text_similarity:.0%}), but this report has no location, "
                    "so an officer must confirm before they are joined."
                ),
            )
        return DedupDecision(
            decision="new",
            score=best.score,
            candidates=candidates,
            explanation="No location and no strongly matching open issue.",
        )

    distance_text = f"{best.distance_m:.0f} m away"
    if best.score >= auto_threshold:
        return DedupDecision(
            decision="merge",
            score=best.score,
            issue=best.issue,
            candidates=candidates,
            explanation=(
                f"Matches {best.issue.issue_code}: wording {best.text_similarity:.0%} similar, "
                f"{distance_text}, reported {best.hours_apart:.0f} h apart."
            ),
        )
    if best.score >= review_threshold:
        return DedupDecision(
            decision="review",
            score=best.score,
            issue=best.issue,
            candidates=candidates,
            explanation=(
                f"Possibly the same as {best.issue.issue_code} (wording "
                f"{best.text_similarity:.0%} similar, {distance_text}), but below the "
                "automatic-merge threshold - sent for human confirmation."
            ),
        )
    return DedupDecision(
        decision="new",
        score=best.score,
        candidates=candidates,
        explanation=(
            f"Closest open issue {best.issue.issue_code} scored {best.score:.2f}, "
            f"below the {review_threshold:.2f} threshold."
        ),
    )
