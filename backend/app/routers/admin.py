"""Officer dashboard API: the queue, the review inbox and every human override.

The rule that shapes this module: **an officer can overrule the AI on anything,
and cannot do so silently.** Category, priority band, cluster membership and
status are all correctable, and each correction requires a written reason that
is copied into the append-only audit log together with the before and after
values.

Nothing here deletes a citizen's report. "Unmerge" moves a report to its own
issue; "merge" links one issue to another and keeps both rows.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config.categories import (
    CATEGORY_KEYS,
    DEPARTMENT_BY_CODE,
    ISSUE_STATUSES,
    STATUS_LABELS_EN,
    department_for_category,
)
from app.config.settings import settings
from app.db import get_db
from app.models import AuditLog, Issue, PipelineStageLog, Report, ReviewTask, StatusEvent
from app.pipeline.orchestrator import refresh_issue_scoring
from app.pipeline.ward import ward_id_for_point
from app.routers.auth import current_officer
from app.schemas import (
    AssignIn,
    CategoryOverrideIn,
    MergeIn,
    PriorityOverrideIn,
    ReviewResolveIn,
    SettingsIn,
    StatusChangeIn,
    audit_entry,
    issue_summary,
    report_public,
    review_task,
    stage_log,
    status_event,
)
from app.security import Officer, new_issue_code
from app.services import audit, equity
from app.services.bootstrap import get_setting, set_setting

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["officer"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _live_issues():
    """Base query excluding issues that were merged into another."""
    return select(Issue).where(Issue.merged_into_id.is_(None))


def _get_issue(db: Session, identifier: str | int) -> Issue:
    """Look an issue up by numeric id or by its ISU- code."""
    issue = None
    if isinstance(identifier, int) or str(identifier).isdigit():
        issue = db.get(Issue, int(identifier))
    if issue is None:
        issue = db.execute(
            select(Issue).where(Issue.issue_code == str(identifier).strip().upper())
        ).scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    return issue


def _record_status(
    db: Session,
    issue: Issue,
    new_status: str,
    officer: Officer,
    note: str = "",
) -> None:
    previous = issue.status
    issue.status = new_status
    issue.updated_at = _utcnow()
    if new_status == "resolved":
        issue.resolved_at = _utcnow()
    elif previous == "resolved":
        issue.resolved_at = None
    db.add(
        StatusEvent(
            issue_id=issue.id,
            from_status=previous,
            to_status=new_status,
            actor=officer.display_name,
            actor_role=officer.role,
            note=note[:500],
        )
    )


# ---------------------------------------------------------------------------
#  Queue
# ---------------------------------------------------------------------------
@router.get("/issues")
def list_issues(
    category: str | None = None,
    ward: str | None = None,
    status: str | None = None,
    band: str | None = None,
    department: str | None = None,
    breached: bool | None = None,
    needs_review: bool | None = None,
    max_age_days: int | None = None,
    q: str | None = None,
    sort: str = Query(default="priority", pattern="^(priority|newest|oldest|reports|sla)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    officer: Officer = Depends(current_officer),
) -> dict:
    """The priority queue, filterable on everything an officer triages by."""
    query = _live_issues()
    if category:
        query = query.where(Issue.category == category)
    if status:
        query = query.where(Issue.status == status)
    else:
        query = query.where(Issue.status != "resolved")
    if band:
        query = query.where(Issue.priority_band == band)
    if department:
        query = query.where(Issue.department == department)
    if breached is not None:
        query = query.where(Issue.sla_breached.is_(breached))
    if ward:
        query = query.join(Issue.ward).where(Issue.ward.has(code=ward))
    if max_age_days is not None:
        cutoff = _utcnow().replace(tzinfo=None)
        from datetime import timedelta

        query = query.where(Issue.created_at >= cutoff - timedelta(days=max_age_days))
    if needs_review:
        review_issue_ids = select(ReviewTask.issue_id).where(ReviewTask.status == "open")
        query = query.where(Issue.id.in_(review_issue_ids))
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(
            or_(
                Issue.title.ilike(pattern),
                Issue.location_text.ilike(pattern),
                Issue.issue_code.ilike(pattern),
            )
        )

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()

    order = {
        "priority": (Issue.priority_score.desc(), Issue.created_at.asc()),
        "newest": (Issue.created_at.desc(),),
        "oldest": (Issue.created_at.asc(),),
        "reports": (Issue.report_count.desc(), Issue.priority_score.desc()),
        "sla": (Issue.sla_deadline.asc().nulls_last(),),
    }[sort]

    issues = db.execute(query.order_by(*order).offset(offset).limit(limit)).scalars().all()
    open_review_counts = dict(
        db.execute(
            select(ReviewTask.issue_id, func.count(ReviewTask.id))
            .where(ReviewTask.status == "open")
            .group_by(ReviewTask.issue_id)
        ).all()
    )

    items = []
    for issue in issues:
        payload = issue_summary(issue)
        payload["open_reviews"] = open_review_counts.get(issue.id, 0)
        items.append(payload)

    return {"total": total, "limit": limit, "offset": offset, "items": items}


@router.get("/issues/{identifier}")
def issue_detail(
    identifier: str,
    db: Session = Depends(get_db),
    officer: Officer = Depends(current_officer),
) -> dict:
    """Everything known about one issue, including how the AI got there."""
    issue = _get_issue(db, identifier)
    reports = db.execute(
        select(Report).where(Report.issue_id == issue.id).order_by(Report.created_at.asc())
    ).scalars().all()

    report_ids = [r.id for r in reports]
    logs = []
    if report_ids:
        logs = db.execute(
            select(PipelineStageLog)
            .where(PipelineStageLog.report_id.in_(report_ids))
            .order_by(PipelineStageLog.report_id.asc(), PipelineStageLog.id.asc())
        ).scalars().all()

    events = db.execute(
        select(StatusEvent)
        .where(StatusEvent.issue_id == issue.id)
        .order_by(StatusEvent.created_at.asc())
    ).scalars().all()

    tasks = db.execute(
        select(ReviewTask).where(ReviewTask.issue_id == issue.id).order_by(ReviewTask.id.asc())
    ).scalars().all()

    merged_children = db.execute(
        select(Issue.issue_code).where(Issue.merged_into_id == issue.id)
    ).scalars().all()

    return {
        "issue": issue_summary(issue),
        "priority_breakdown": issue.priority_breakdown or [],
        "priority_override_reason": issue.priority_override_reason,
        "reports": [report_public(report) for report in reports],
        "timeline": [status_event(event) for event in events],
        "stage_logs": [stage_log(log) for log in logs],
        "review_tasks": [review_task(task) for task in tasks],
        "audit": [audit_entry(entry) for entry in audit.for_entity(db, "issue", issue.id)],
        "merged_from": list(merged_children),
        "merged_into": (
            db.get(Issue, issue.merged_into_id).issue_code if issue.merged_into_id else None
        ),
    }


# ---------------------------------------------------------------------------
#  Officer actions
# ---------------------------------------------------------------------------
@router.patch("/issues/{identifier}/status")
def change_status(
    identifier: str,
    payload: StatusChangeIn,
    db: Session = Depends(get_db),
    officer: Officer = Depends(current_officer),
) -> dict:
    issue = _get_issue(db, identifier)
    if payload.status == issue.status:
        raise HTTPException(status_code=409, detail=f"Already {STATUS_LABELS_EN[payload.status]}")

    before = {"status": issue.status}
    _record_status(db, issue, payload.status, officer, payload.note)
    refresh_issue_scoring(db, issue)
    audit.record(
        db,
        actor=officer.display_name,
        actor_role=officer.role,
        action="change_status",
        entity_type="issue",
        entity_id=issue.id,
        before=before,
        after={"status": issue.status},
        reason=payload.note or f"Moved to {STATUS_LABELS_EN[payload.status]}",
    )
    db.commit()
    equity.invalidate_cache()
    return {"ok": True, "issue": issue_summary(issue)}


@router.patch("/issues/{identifier}/assign")
def assign_issue(
    identifier: str,
    payload: AssignIn,
    db: Session = Depends(get_db),
    officer: Officer = Depends(current_officer),
) -> dict:
    issue = _get_issue(db, identifier)
    if payload.department not in DEPARTMENT_BY_CODE:
        raise HTTPException(status_code=422, detail="Unknown department")

    before = {"department": issue.department, "assigned_to": issue.assigned_to}
    issue.department = payload.department
    issue.assigned_to = payload.assigned_to.strip() or DEPARTMENT_BY_CODE[payload.department].short
    issue.assigned_at = _utcnow()
    if issue.status in {"received", "verified"}:
        _record_status(
            db,
            issue,
            "assigned",
            officer,
            payload.note or f"Routed to {DEPARTMENT_BY_CODE[payload.department].name}",
        )
    audit.record(
        db,
        actor=officer.display_name,
        actor_role=officer.role,
        action="assign",
        entity_type="issue",
        entity_id=issue.id,
        before=before,
        after={"department": issue.department, "assigned_to": issue.assigned_to},
        reason=payload.note or "Work order routed",
    )
    db.commit()
    return {"ok": True, "issue": issue_summary(issue)}


@router.post("/issues/{identifier}/override-category")
def override_category(
    identifier: str,
    payload: CategoryOverrideIn,
    db: Session = Depends(get_db),
    officer: Officer = Depends(current_officer),
) -> dict:
    """Correct the AI's classification. Reason mandatory; SLA and priority recomputed."""
    if payload.category not in CATEGORY_KEYS:
        raise HTTPException(status_code=422, detail="Unknown category")
    issue = _get_issue(db, identifier)
    if payload.category == issue.category:
        raise HTTPException(status_code=409, detail="That is already the category")

    before = {
        "category": issue.category,
        "department": issue.department,
        "sla_hours": issue.sla_hours,
        "priority_score": issue.priority_score,
    }
    issue.category = payload.category
    issue.department = department_for_category(payload.category)
    result = refresh_issue_scoring(db, issue)

    audit.record(
        db,
        actor=officer.display_name,
        actor_role=officer.role,
        action="override_category",
        entity_type="issue",
        entity_id=issue.id,
        before=before,
        after={
            "category": issue.category,
            "department": issue.department,
            "sla_hours": issue.sla_hours,
            "priority_score": result.score,
        },
        reason=payload.reason,
    )
    db.commit()
    return {"ok": True, "issue": issue_summary(issue), "priority_breakdown": result.as_dict()}


@router.post("/issues/{identifier}/override-priority")
def override_priority(
    identifier: str,
    payload: PriorityOverrideIn,
    db: Session = Depends(get_db),
    officer: Officer = Depends(current_officer),
) -> dict:
    """Pin an issue to a band, or release it back to the computed score."""
    issue = _get_issue(db, identifier)
    before = {"band": issue.priority_band, "override": issue.priority_override_band}

    issue.priority_override_band = payload.band
    issue.priority_override_reason = payload.reason if payload.band else None
    refresh_issue_scoring(db, issue)

    audit.record(
        db,
        actor=officer.display_name,
        actor_role=officer.role,
        action="override_priority",
        entity_type="issue",
        entity_id=issue.id,
        before=before,
        after={"band": issue.priority_band, "override": issue.priority_override_band},
        reason=payload.reason,
    )
    db.commit()
    return {"ok": True, "issue": issue_summary(issue)}


@router.post("/issues/{identifier}/merge")
def merge_issues(
    identifier: str,
    payload: MergeIn,
    db: Session = Depends(get_db),
    officer: Officer = Depends(current_officer),
) -> dict:
    """Merge this issue INTO the target. Both rows survive; reports move across."""
    source = _get_issue(db, identifier)
    target = _get_issue(db, payload.target_issue_code)
    if source.id == target.id:
        raise HTTPException(status_code=422, detail="An issue cannot be merged into itself")
    if target.merged_into_id is not None:
        raise HTTPException(status_code=409, detail="The target issue has itself been merged")

    moved = db.execute(select(Report).where(Report.issue_id == source.id)).scalars().all()
    for report in moved:
        report.issue_id = target.id

    target.report_count = (target.report_count or 0) + (source.report_count or 0)
    target.severity = max(int(target.severity or 1), int(source.severity or 1))
    target.hazard_flags = list(
        dict.fromkeys([*(target.hazard_flags or []), *(source.hazard_flags or [])])
    )
    target.languages = list(
        dict.fromkeys([*(target.languages or []), *(source.languages or [])])
    )
    if target.lat is None and source.lat is not None:
        target.lat, target.lon, target.ward_id = source.lat, source.lon, source.ward_id

    source.merged_into_id = target.id
    source.updated_at = _utcnow()
    result = refresh_issue_scoring(db, target)

    db.add(
        StatusEvent(
            issue_id=target.id,
            from_status=target.status,
            to_status=target.status,
            actor=officer.display_name,
            actor_role=officer.role,
            note=f"{len(moved)} report(s) merged in from {source.issue_code}: {payload.reason}",
        )
    )
    audit.record(
        db,
        actor=officer.display_name,
        actor_role=officer.role,
        action="merge_issues",
        entity_type="issue",
        entity_id=source.id,
        before={"issue": source.issue_code, "report_count": len(moved)},
        after={"merged_into": target.issue_code, "target_report_count": target.report_count},
        reason=payload.reason,
    )
    db.commit()
    return {
        "ok": True,
        "merged_reports": len(moved),
        "target": issue_summary(target),
        "priority_breakdown": result.as_dict(),
    }


@router.post("/reports/{report_id}/unmerge")
def unmerge_report(
    report_id: int,
    payload: MergeIn | None = None,
    reason: str = Query(default="", max_length=500),
    db: Session = Depends(get_db),
    officer: Officer = Depends(current_officer),
) -> dict:
    """Split one report out of its cluster into an issue of its own."""
    explanation = (payload.reason if payload else "") or reason
    if len(explanation.strip()) < 8:
        raise HTTPException(status_code=422, detail="Please give a short reason (8+ characters)")

    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    old_issue = db.get(Issue, report.issue_id) if report.issue_id else None
    if old_issue is None:
        raise HTTPException(status_code=409, detail="This report is not attached to an issue")
    if (old_issue.report_count or 0) <= 1:
        raise HTTPException(status_code=409, detail="This issue has only one report")

    new_issue = Issue(
        issue_code=new_issue_code(),
        title=report.summary_en or old_issue.title,
        category=report.category or old_issue.category,
        sub_issue=report.sub_issue,
        status="received",
        lat=report.lat,
        lon=report.lon,
        location_text=report.location_text,
        ward_id=report.ward_id,
        report_count=1,
        severity=report.severity or 3,
        hazard_flags=list(report.hazard_flags or []),
        languages=[report.language] if report.language else [],
        department=department_for_category(report.category or "other"),
        created_at=report.created_at,
    )
    db.add(new_issue)
    db.flush()

    report.issue_id = new_issue.id
    report.dedup_decision = "unmerged"
    old_issue.report_count = max(1, (old_issue.report_count or 1) - 1)

    db.add(
        StatusEvent(
            issue_id=new_issue.id,
            from_status=None,
            to_status="received",
            actor=officer.display_name,
            actor_role=officer.role,
            note=f"Separated from {old_issue.issue_code}: {explanation}",
        )
    )
    refresh_issue_scoring(db, new_issue)
    refresh_issue_scoring(db, old_issue)

    audit.record(
        db,
        actor=officer.display_name,
        actor_role=officer.role,
        action="unmerge_report",
        entity_type="report",
        entity_id=report.id,
        before={"issue": old_issue.issue_code},
        after={"issue": new_issue.issue_code},
        reason=explanation,
    )
    db.commit()
    return {"ok": True, "new_issue": issue_summary(new_issue), "source": issue_summary(old_issue)}


# ---------------------------------------------------------------------------
#  Review queue
# ---------------------------------------------------------------------------
@router.get("/review")
def review_queue(
    kind: str | None = None,
    status: str = Query(default="open", pattern="^(open|resolved|all)$"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    officer: Officer = Depends(current_officer),
) -> dict:
    """Work items where the AI deliberately deferred to a human."""
    query = select(ReviewTask)
    if status != "all":
        query = query.where(ReviewTask.status == status)
    if kind:
        query = query.where(ReviewTask.kind == kind)

    tasks = db.execute(
        query.order_by(ReviewTask.status.asc(), ReviewTask.created_at.asc()).limit(limit)
    ).scalars().all()

    report_ids = [t.report_id for t in tasks if t.report_id]
    reports = {
        r.id: r
        for r in db.execute(select(Report).where(Report.id.in_(report_ids))).scalars().all()
    } if report_ids else {}

    candidate_ids = [t.candidate_issue_id for t in tasks if t.candidate_issue_id]
    candidates = {
        i.id: i
        for i in db.execute(select(Issue).where(Issue.id.in_(candidate_ids))).scalars().all()
    } if candidate_ids else {}

    items = []
    for task in tasks:
        payload = review_task(task, report=reports.get(task.report_id))
        candidate = candidates.get(task.candidate_issue_id)
        payload["candidate_issue"] = issue_summary(candidate) if candidate else None
        items.append(payload)

    counts = dict(
        db.execute(
            select(ReviewTask.kind, func.count(ReviewTask.id))
            .where(ReviewTask.status == "open")
            .group_by(ReviewTask.kind)
        ).all()
    )
    return {"items": items, "open_counts": counts, "open_total": sum(counts.values())}


@router.post("/review/{task_id}/resolve")
def resolve_review(
    task_id: int,
    payload: ReviewResolveIn,
    db: Session = Depends(get_db),
    officer: Officer = Depends(current_officer),
) -> dict:
    """Close a review item by confirming or correcting what the AI proposed."""
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Review task not found")
    if task.status != "open":
        raise HTTPException(status_code=409, detail="This review item is already closed")

    report = db.get(Report, task.report_id) if task.report_id else None
    issue = db.get(Issue, task.issue_id) if task.issue_id else None
    outcome: dict = {"action": payload.action}

    if payload.action == "recategorise":
        if not payload.category or payload.category not in CATEGORY_KEYS:
            raise HTTPException(status_code=422, detail="A valid category is required")
        if issue is None:
            raise HTTPException(status_code=409, detail="No issue attached to this review item")
        before = {"category": issue.category}
        issue.category = payload.category
        issue.department = department_for_category(payload.category)
        if report is not None:
            report.category = payload.category
            report.ai_source = "officer"
            report.confidence = 1.0
        refresh_issue_scoring(db, issue)
        audit.record(
            db,
            actor=officer.display_name,
            actor_role=officer.role,
            action="override_category",
            entity_type="issue",
            entity_id=issue.id,
            before=before,
            after={"category": issue.category},
            reason=payload.reason,
        )
        outcome["category"] = payload.category

    elif payload.action == "set_location":
        if payload.lat is None or payload.lon is None:
            raise HTTPException(status_code=422, detail="Latitude and longitude are required")
        if report is None:
            raise HTTPException(status_code=409, detail="No report attached to this review item")
        before = {"lat": report.lat, "lon": report.lon}
        report.lat, report.lon = payload.lat, payload.lon
        report.location_source = "officer_pin"
        report.location_confidence = 1.0
        if payload.location_text:
            report.location_text = payload.location_text[:300]
        report.ward_id = ward_id_for_point(db, payload.lat, payload.lon)
        if issue is not None:
            issue.lat, issue.lon, issue.ward_id = payload.lat, payload.lon, report.ward_id
            if payload.location_text:
                issue.location_text = payload.location_text[:300]
            refresh_issue_scoring(db, issue)
        audit.record(
            db,
            actor=officer.display_name,
            actor_role=officer.role,
            action="set_location",
            entity_type="report",
            entity_id=report.id,
            before=before,
            after={"lat": payload.lat, "lon": payload.lon},
            reason=payload.reason,
        )
        outcome["location"] = {"lat": payload.lat, "lon": payload.lon}

    elif payload.action == "merge":
        candidate = db.get(Issue, task.candidate_issue_id) if task.candidate_issue_id else None
        if candidate is None or issue is None:
            raise HTTPException(status_code=409, detail="No duplicate candidate to merge with")
        if candidate.id == issue.id:
            raise HTTPException(status_code=409, detail="Already the same issue")
        merged = merge_issues(
            str(issue.id),
            MergeIn(reason=payload.reason, target_issue_code=candidate.issue_code),
            db=db,
            officer=officer,
        )
        outcome["merged_into"] = candidate.issue_code
        outcome["merged_reports"] = merged["merged_reports"]

    elif payload.action in {"confirm", "keep_separate"}:
        audit.record(
            db,
            actor=officer.display_name,
            actor_role=officer.role,
            action=f"review_{payload.action}",
            entity_type="review_task",
            entity_id=task.id,
            before={"kind": task.kind},
            after={"decision": payload.action},
            reason=payload.reason,
        )

    task.status = "resolved"
    task.resolved_by = officer.display_name
    task.resolved_at = _utcnow()
    task.reason = payload.reason
    task.resolution = outcome

    if report is not None:
        still_open = db.execute(
            select(func.count(ReviewTask.id)).where(
                ReviewTask.report_id == report.id, ReviewTask.status == "open"
            )
        ).scalar_one()
        if still_open == 0:
            report.needs_review = False
            report.review_reason = ""

    db.commit()
    return {"ok": True, "resolution": outcome}


# ---------------------------------------------------------------------------
#  Audit, settings, demo
# ---------------------------------------------------------------------------
@router.get("/audit")
def audit_log(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    action: str | None = None,
    db: Session = Depends(get_db),
    officer: Officer = Depends(current_officer),
) -> dict:
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    entries = db.execute(
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset(offset).limit(limit)
    ).scalars().all()
    actions = [
        row[0] for row in db.execute(select(AuditLog.action).distinct().order_by(AuditLog.action))
    ]
    return {
        "total": total,
        "items": [audit_entry(entry) for entry in entries],
        "actions": actions,
    }


@router.get("/settings")
def read_settings(
    db: Session = Depends(get_db), officer: Officer = Depends(current_officer)
) -> dict:
    return {
        "equity_boost_enabled": bool(get_setting(db, "equity_boost_enabled", True)),
        "demo_mode": settings.demo_mode,
        "llm_provider": settings.llm_provider,
        "llm_active": settings.llm_active,
    }


@router.patch("/settings")
def update_settings(
    payload: SettingsIn,
    db: Session = Depends(get_db),
    officer: Officer = Depends(current_officer),
) -> dict:
    """Flip a policy switch. Every change is audited, including who and why."""
    if payload.equity_boost_enabled is None:
        raise HTTPException(status_code=422, detail="Nothing to change")

    before = bool(get_setting(db, "equity_boost_enabled", True))
    set_setting(db, "equity_boost_enabled", payload.equity_boost_enabled, actor=officer.username)

    # Re-score every open issue so the change is visible immediately.
    equity.invalidate_cache()
    open_issues = db.execute(_live_issues().where(Issue.status != "resolved")).scalars().all()
    for issue in open_issues:
        refresh_issue_scoring(db, issue, equity_enabled=payload.equity_boost_enabled)

    audit.record(
        db,
        actor=officer.display_name,
        actor_role=officer.role,
        action="toggle_equity_boost",
        entity_type="policy",
        entity_id="equity_boost_enabled",
        before={"enabled": before},
        after={"enabled": payload.equity_boost_enabled},
        reason=payload.reason or "Equity boost toggled from the dashboard",
    )
    db.commit()
    return {
        "ok": True,
        "equity_boost_enabled": payload.equity_boost_enabled,
        "issues_rescored": len(open_issues),
    }


@router.post("/demo/reset")
def demo_reset(
    officer: Officer = Depends(current_officer),
    db: Session = Depends(get_db),
) -> dict:
    """Rebuild the demo dataset. Available only when DEMO_MODE is on."""
    if not settings.demo_mode:
        raise HTTPException(status_code=403, detail="DEMO_MODE is off")
    from app.services.demo import reseed

    summary = reseed(db)
    equity.invalidate_cache()
    return {"ok": True, **summary}
