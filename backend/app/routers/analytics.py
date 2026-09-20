"""Analytics: SLA performance, the equity audit, and AI health.

These three endpoints are the accountability half of the product. The SLA view
says whether the city is keeping its promises; the equity view says whether it
is keeping them *equally*; the AI health view says how much of that the machine
got right, and admits where it did not.

Every number here is computed live from the database. The held-out benchmark
figures come from ``scripts/evaluate.py`` and are stored as an ``EvalRun`` -
they are reported separately and never mixed with live counters, because one is
a controlled measurement and the other is operational reality.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config.categories import CATEGORY_BY_KEY, DEPARTMENT_BY_CODE
from app.config.settings import settings
from app.db import get_db
from app.models import EvalRun, Issue, PipelineStageLog, Report, ReviewTask, Ward
from app.pipeline.embed import get_embedder
from app.pipeline.fallback_clf import load_model
from app.pipeline.llm.base import get_provider
from app.pipeline.understand import cache_stats
from app.services.equity import build_equity_report

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _percentile(values: list[float], fraction: float) -> float | None:
    """Nearest-rank percentile. Small-sample safe, unlike quantiles()."""
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1)))))
    return round(ordered[index], 1)


def _resolution_hours(created_at, resolved_at) -> float | None:
    start, end = _aware(created_at), _aware(resolved_at)
    if start is None or end is None:
        return None
    return max(0.0, (end - start).total_seconds() / 3600.0)


@router.get("/sla")
def sla_dashboard(db: Session = Depends(get_db)) -> dict:
    """Open vs resolved, breaches by department and ward, ageing, and trend."""
    issues = list(
        db.execute(select(Issue).where(Issue.merged_into_id.is_(None))).scalars().all()
    )
    wards = {w.id: w for w in db.execute(select(Ward)).scalars().all()}
    now = datetime.now(timezone.utc)

    resolved = [i for i in issues if i.resolved_at is not None]
    open_issues = [i for i in issues if i.resolved_at is None]
    durations = [
        d for d in (_resolution_hours(i.created_at, i.resolved_at) for i in resolved) if d
    ]
    breached_open = [i for i in open_issues if i.sla_breached]

    def group_stats(key_fn, label_fn) -> list[dict]:
        buckets: dict[str, dict] = {}
        for issue in issues:
            key = key_fn(issue)
            if key is None:
                continue
            bucket = buckets.setdefault(
                key,
                {
                    "key": key,
                    "label": label_fn(key),
                    "open": 0,
                    "resolved": 0,
                    "breached": 0,
                    "_durations": [],
                },
            )
            if issue.resolved_at is not None:
                bucket["resolved"] += 1
                duration = _resolution_hours(issue.created_at, issue.resolved_at)
                if duration is not None:
                    bucket["_durations"].append(duration)
            else:
                bucket["open"] += 1
            if issue.sla_breached:
                bucket["breached"] += 1

        output = []
        for bucket in buckets.values():
            total = bucket["open"] + bucket["resolved"]
            values = bucket.pop("_durations")
            bucket["total"] = total
            bucket["breach_rate"] = round(bucket["breached"] / total, 4) if total else 0.0
            bucket["median_hours"] = round(statistics.median(values), 1) if values else None
            output.append(bucket)
        return sorted(output, key=lambda b: -b["total"])

    # Backlog ageing on still-open issues.
    buckets = [("0-1 day", 0, 1), ("1-3 days", 1, 3), ("3-7 days", 3, 7),
               ("1-2 weeks", 7, 14), ("2-4 weeks", 14, 30), ("30+ days", 30, 10_000)]
    ageing = []
    for label, low, high in buckets:
        count = 0
        for issue in open_issues:
            created = _aware(issue.created_at)
            if created is None:
                continue
            age_days = (now - created).total_seconds() / 86400.0
            if low <= age_days < high:
                count += 1
        ageing.append({"bucket": label, "count": count})

    # 30-day created vs resolved trend.
    trend: list[dict] = []
    for offset in range(29, -1, -1):
        day = (now - timedelta(days=offset)).date()
        created_count = sum(
            1 for i in issues if _aware(i.created_at) and _aware(i.created_at).date() == day
        )
        resolved_count = sum(
            1 for i in issues if _aware(i.resolved_at) and _aware(i.resolved_at).date() == day
        )
        trend.append({"date": day.isoformat(), "created": created_count, "resolved": resolved_count})

    return {
        "summary": {
            "total_issues": len(issues),
            "open": len(open_issues),
            "resolved": len(resolved),
            "breached_open": len(breached_open),
            "breach_rate": round(
                sum(1 for i in issues if i.sla_breached) / len(issues), 4
            ) if issues else 0.0,
            "median_resolution_hours": round(statistics.median(durations), 1) if durations else None,
            "p90_resolution_hours": _percentile(durations, 0.9),
            "on_time_rate": round(
                sum(1 for i in resolved if not i.sla_breached) / len(resolved), 4
            ) if resolved else None,
        },
        "by_department": group_stats(
            lambda i: i.department,
            lambda k: DEPARTMENT_BY_CODE[k].short if k in DEPARTMENT_BY_CODE else k,
        ),
        "by_ward": group_stats(
            lambda i: wards[i.ward_id].code if i.ward_id in wards else None,
            lambda k: next((w.name for w in wards.values() if w.code == k), k),
        ),
        "by_category": group_stats(
            lambda i: i.category,
            lambda k: CATEGORY_BY_KEY[k].label_en if k in CATEGORY_BY_KEY else k,
        ),
        "backlog_ageing": ageing,
        "trend": trend,
    }


@router.get("/equity")
def equity_dashboard(db: Session = Depends(get_db)) -> dict:
    """Ward and language service parity, with the thresholds used to flag."""
    report = build_equity_report(db)
    payload = report.as_dict()
    payload["explanation"] = (
        "A ward or language group is flagged when its median time-to-resolve is at least "
        f"{report.thresholds['underserved_ratio']}x the city median, or its SLA breach rate "
        f"exceeds the city rate by {report.thresholds['underserved_breach_margin']:.0%}. "
        f"Groups with fewer than {report.thresholds['min_resolved_sample']} resolved issues "
        "are never flagged, because a small sample is not evidence."
    )
    payload["equity_boost_note"] = (
        f"Flagged wards currently receive +{report.thresholds['equity_points']} priority points. "
        "The adjustment is shown in every score breakdown and can be switched off."
    )
    return payload


@router.get("/ai-health")
def ai_health(db: Session = Depends(get_db)) -> dict:
    """How the AI is actually performing: live counters plus the held-out benchmark."""
    reports = list(db.execute(select(Report)).scalars().all())
    total = len(reports)

    by_source: dict[str, int] = {}
    confidences: list[float] = []
    for report in reports:
        by_source[report.ai_source] = by_source.get(report.ai_source, 0) + 1
        if report.confidence:
            confidences.append(report.confidence)

    dedup_counts: dict[str, int] = {}
    for report in reports:
        dedup_counts[report.dedup_decision] = dedup_counts.get(report.dedup_decision, 0) + 1

    live_issue_count = db.execute(
        select(func.count(Issue.id)).where(Issue.merged_into_id.is_(None))
    ).scalar_one()

    located = sum(1 for r in reports if r.lat is not None)
    location_sources: dict[str, int] = {}
    for report in reports:
        location_sources[report.location_source] = location_sources.get(report.location_source, 0) + 1

    review_open = dict(
        db.execute(
            select(ReviewTask.kind, func.count(ReviewTask.id))
            .where(ReviewTask.status == "open")
            .group_by(ReviewTask.kind)
        ).all()
    )
    review_resolved = db.execute(
        select(func.count(ReviewTask.id)).where(ReviewTask.status == "resolved")
    ).scalar_one()

    # Latency, overall and per stage.
    pipeline_times = [float(r.pipeline_ms) for r in reports if r.pipeline_ms]
    stage_rows = db.execute(
        select(PipelineStageLog.stage, PipelineStageLog.duration_ms, PipelineStageLog.status)
    ).all()
    stage_times: dict[str, list[float]] = {}
    stage_fallbacks: dict[str, int] = {}
    for stage, duration_ms, status in stage_rows:
        stage_times.setdefault(stage, []).append(float(duration_ms or 0))
        if status in {"fallback", "error"}:
            stage_fallbacks[stage] = stage_fallbacks.get(stage, 0) + 1

    stage_summary = [
        {
            "stage": stage,
            "runs": len(values),
            "p50_ms": _percentile(values, 0.5),
            "p95_ms": _percentile(values, 0.95),
            "fallback_or_error": stage_fallbacks.get(stage, 0),
        }
        for stage, values in sorted(stage_times.items(), key=lambda pair: -len(pair[1]))
    ]

    latest_eval = db.execute(
        select(EvalRun).order_by(EvalRun.created_at.desc()).limit(1)
    ).scalar_one_or_none()

    provider = get_provider()
    collapsed = max(0, total - live_issue_count)

    return {
        "components": {
            "llm_provider": settings.llm_provider,
            "llm_active": settings.llm_active and provider.available,
            "llm_model": provider.describe(),
            "offline_classifier_trained": load_model() is not None,
            "embedder": get_embedder().name,
            "cached_llm_responses": cache_stats()["entries"],
        },
        "live": {
            "total_reports": total,
            "total_issues": live_issue_count,
            "reports_collapsed": collapsed,
            "triage_work_saved_pct": round(100.0 * collapsed / total, 1) if total else 0.0,
            "by_source": by_source,
            "mean_confidence": round(statistics.mean(confidences), 3) if confidences else None,
            "low_confidence_share": round(
                sum(1 for c in confidences if c < 0.55) / len(confidences), 3
            ) if confidences else None,
            "dedup_decisions": dedup_counts,
            "geocode": {
                "resolved_rate": round(located / total, 4) if total else None,
                "by_source": location_sources,
            },
            "review": {
                "open_by_kind": review_open,
                "open_total": sum(review_open.values()),
                "resolved_total": review_resolved,
            },
            "latency": {
                "pipeline_p50_ms": _percentile(pipeline_times, 0.5),
                "pipeline_p95_ms": _percentile(pipeline_times, 0.95),
                "by_stage": stage_summary,
            },
        },
        "holdout": latest_eval.report if latest_eval is not None else None,
        "holdout_run_at": (
            _aware(latest_eval.created_at).isoformat() if latest_eval is not None else None
        ),
        "note": (
            "Live figures describe this database. Held-out figures come from "
            "scripts/evaluate.py on a labelled split that the model never trained on."
        ),
    }
