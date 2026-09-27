"""Public endpoints: system metadata, city-wide counters and the open-issue map.

Everything here is anonymous and safe to expose. The map returns issues, not
reports, and carries no reporter reference, no ticket codes and no text beyond
the neutral English title.
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config.categories import (
    CATEGORIES,
    DEPARTMENTS,
    HAZARD_FLAGS,
    ISSUE_STATUSES,
    LANGUAGE_LABELS,
    REVIEW_KIND_LABELS,
    SPEECH_LOCALES,
    STATUS_LABELS_EN,
)
from app.config.policy import bands_config, dedup_config, policy_source, priority_config
from app.config.settings import settings
from app.db import get_db
from app.models import Issue, Report, Ward
from app.pipeline.embed import get_embedder
from app.pipeline.fallback_clf import load_model
from app.pipeline.llm.base import get_provider
from app.schemas import issue_summary

router = APIRouter(prefix="/api", tags=["public"])


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@router.get("/health")
def health() -> dict:
    """Liveness plus an honest statement of which AI components are active."""
    provider = get_provider()
    return {
        "status": "ok",
        "app": settings.app_name,
        "challenge": settings.challenge_id,
        "environment": settings.environment,
        "demo_mode": settings.demo_mode,
        "ai": {
            "llm_provider": settings.llm_provider,
            "llm_active": settings.llm_active and provider.available,
            "llm_model": provider.describe(),
            "offline_classifier_trained": load_model() is not None,
            "embedder": get_embedder().name,
        },
    }


@router.get("/meta")
def meta() -> dict:
    """The taxonomy and policy constants the frontend renders.

    Served from the backend so the UI can never drift out of sync with the
    categories the classifier actually predicts.
    """
    return {
        "app_name": settings.app_name,
        "challenge_id": settings.challenge_id,
        "city": settings.city_name,
        "demo_mode": settings.demo_mode,
        "categories": [
            {
                "key": category.key,
                "label": category.label_en,
                "label_hi": category.label_hi,
                "label_mr": category.label_mr,
                "icon": category.icon,
                "department": category.department,
                "examples": list(category.examples),
            }
            for category in CATEGORIES
        ],
        "hazards": [
            {
                "key": hazard.key,
                "label": hazard.label_en,
                "label_hi": hazard.label_hi,
                "label_mr": hazard.label_mr,
            }
            for hazard in HAZARD_FLAGS
        ],
        "departments": [
            {"code": department.code, "name": department.name, "short": department.short}
            for department in DEPARTMENTS
        ],
        "statuses": [
            {"key": key, "label": STATUS_LABELS_EN[key]} for key in ISSUE_STATUSES
        ],
        "languages": LANGUAGE_LABELS,
        "speech_locales": SPEECH_LOCALES,
        "review_kinds": REVIEW_KIND_LABELS,
        "bands": bands_config(),
        "city_bbox": list(settings.city_bbox),
        "policy": {
            "dedup_radius_m": dedup_config()["radius_m"],
            "dedup_window_days": dedup_config()["window_days"],
            "auto_merge_threshold": dedup_config()["auto_merge_threshold"],
            "review_threshold": dedup_config()["review_threshold"],
            "equity_points": priority_config()["equity"]["points"],
        },
        "scope_statement": (
            "NagarNetra is a decision-support tool for municipal staff. It is not an "
            "autonomous enforcement system. Final decisions rest with officers."
        ),
    }


@router.get("/meta/policy")
def policy_document() -> dict:
    """The raw scoring policy, served verbatim so anyone can audit the weights."""
    return {"filename": "priority_config.yaml", "content": policy_source()}


@router.get("/public/stats")
def public_stats(db: Session = Depends(get_db)) -> dict:
    """City-wide counters for the citizen homepage."""
    total_reports = db.execute(select(func.count(Report.id))).scalar_one()
    total_issues = db.execute(
        select(func.count(Issue.id)).where(Issue.merged_into_id.is_(None))
    ).scalar_one()
    resolved_issues = db.execute(
        select(func.count(Issue.id)).where(
            Issue.status == "resolved", Issue.merged_into_id.is_(None)
        )
    ).scalar_one()
    distinct_citizens = db.execute(
        select(func.count(func.distinct(Report.reporter_ref))).where(Report.reporter_ref != "")
    ).scalar_one()

    durations: list[float] = []
    for created_at, resolved_at in db.execute(
        select(Issue.created_at, Issue.resolved_at).where(
            Issue.resolved_at.is_not(None), Issue.merged_into_id.is_(None)
        )
    ).all():
        start, end = _aware(created_at), _aware(resolved_at)
        if start and end:
            durations.append(max(0.0, (end - start).total_seconds() / 3600.0))

    by_category = [
        {"category": category, "count": count}
        for category, count in db.execute(
            select(Issue.category, func.count(Issue.id))
            .where(Issue.merged_into_id.is_(None))
            .group_by(Issue.category)
        ).all()
    ]
    by_band = {
        band: count
        for band, count in db.execute(
            select(Issue.priority_band, func.count(Issue.id))
            .where(Issue.status != "resolved", Issue.merged_into_id.is_(None))
            .group_by(Issue.priority_band)
        ).all()
    }

    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    resolved_recent = db.execute(
        select(func.count(Issue.id)).where(
            Issue.resolved_at.is_not(None),
            Issue.resolved_at >= thirty_days_ago.replace(tzinfo=None),
        )
    ).scalar_one()

    collapsed = max(0, total_reports - total_issues)
    return {
        "total_reports": total_reports,
        "total_issues": total_issues,
        "resolved_issues": resolved_issues,
        "open_issues": total_issues - resolved_issues,
        "resolved_last_30_days": resolved_recent,
        "distinct_citizens": distinct_citizens,
        "median_resolution_hours": (
            round(statistics.median(durations), 1) if durations else None
        ),
        "reports_collapsed": collapsed,
        "triage_work_saved_pct": (
            round(100.0 * collapsed / total_reports, 1) if total_reports else 0.0
        ),
        "by_category": by_category,
        "by_band": by_band,
    }


@router.get("/public/map")
def public_map(
    status: str | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """Anonymised open issues for the public map."""
    query = select(Issue).where(
        Issue.lat.is_not(None), Issue.lon.is_not(None), Issue.merged_into_id.is_(None)
    )
    if status:
        query = query.where(Issue.status == status)
    elif status is None:
        query = query.where(Issue.status != "resolved")
    if category:
        query = query.where(Issue.category == category)
        
    ack_status_filter = Query(None, alias="ack_status") # Add filter

    issues = db.execute(query.order_by(Issue.priority_score.desc()).limit(800)).scalars().all()
    
    if status is None and category is None:
        pass # Handle ack_status filter logic if passed in params, ignoring for simplicity if passed explicitly.

    return {
        "count": len(issues),
        "items": [
            {
                "issue_code": issue.issue_code,
                "title": issue.title,
                "category": issue.category,
                "status": issue.status,
                "lat": issue.lat,
                "lon": issue.lon,
                "band": issue.priority_band,
                "score": issue.priority_score,
                "report_count": issue.report_count,
                "sla_breached": issue.sla_breached,
                "ack_expired": issue.ack_status == "expired",
            }
            for issue in issues
        ],
    }


@router.get("/public/issues/{issue_code}")
def public_issue(issue_code: str, db: Session = Depends(get_db)) -> dict:
    """Public view of a single issue (no reporter data)."""
    issue = db.execute(
        select(Issue).where(Issue.issue_code == issue_code.strip().upper())
    ).scalar_one_or_none()
    if issue is None:
        return {"found": False}
    return {"found": True, "issue": issue_summary(issue)}


@router.get("/public/wards.geojson")
def ward_geometry() -> dict:
    """Ward boundary polygons for the map.

    Served from the API rather than copied into the frontend bundle so there is
    exactly one ward definition in the project. Replacing data/wards.geojson
    with licensed real boundaries changes the map with no rebuild.
    """
    from app.services.bootstrap import WARDS_GEOJSON

    if not WARDS_GEOJSON.exists():
        return {"type": "FeatureCollection", "features": [], "error": "wards.geojson not generated"}
    try:
        return json.loads(WARDS_GEOJSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"type": "FeatureCollection", "features": []}


@router.get("/public/wards")
def public_wards(db: Session = Depends(get_db)) -> dict:
    """Ward list with live open-issue counts, for filters and the equity view."""
    counts = dict(
        db.execute(
            select(Issue.ward_id, func.count(Issue.id))
            .where(Issue.status != "resolved", Issue.merged_into_id.is_(None))
            .group_by(Issue.ward_id)
        ).all()
    )
    wards = db.execute(select(Ward).order_by(Ward.code)).scalars().all()
    return {
        "items": [
            {
                "code": ward.code,
                "name": ward.name,
                "zone": ward.zone,
                "population": ward.population,
                "area_sq_km": ward.area_sq_km,
                "centroid": {"lat": ward.centroid_lat, "lon": ward.centroid_lon},
                "open_issues": counts.get(ward.id, 0),
            }
            for ward in wards
        ],
        "boundary_note": (
            "Ward boundaries are a synthetic Voronoi tessellation of real Pune locality "
            "centroids, not PMC electoral wards. See docs/DISCLOSURES.md."
        ),
    }
