"""Citizen-facing complaint intake and tracking.

The contract with the citizen:

* Every submission gets a ticket code. Nothing is refused by the AI.
* The response explains, in plain language, what the system understood and why.
* If the complaint duplicates an existing one, the citizen is told that others
  reported it and that their report raised its priority - never "rejected".
* If the AI was unsure, the citizen is told a person will look. That is framed
  as the system doing its job, because it is.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.categories import STATUS_LABELS_EN
from app.db import get_db, session_scope
from app.models import Feedback, Issue, Report, StatusEvent
from app.pipeline import image as image_stage
from app.pipeline.orchestrator import refresh_issue_scoring, run_pipeline
from app.schemas import (
    FeedbackIn,
    category_block,
    hazard_blocks,
    issue_summary,
    report_public,
    sla_block,
    status_event,
)
from app.security import encrypt_text, hash_reference, new_ticket_code

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["citizen"])

MAX_TEXT_LENGTH = 4000


def _rescore_cluster(issue_id: int) -> None:
    """Background pass: refresh scoring after a submission has been answered.

    The citizen already has their ticket by the time this runs. Keeping it out
    of the request means an expensive equity recompute can never make a
    complaint form feel slow.
    """
    db = session_scope()
    try:
        issue = db.get(Issue, issue_id)
        if issue is not None:
            refresh_issue_scoring(db, issue)
            db.commit()
    except Exception:  # noqa: BLE001 - background work must never surface
        logger.exception("Background rescore failed for issue %s", issue_id)
        db.rollback()
    finally:
        db.close()


@router.post("/complaints", status_code=201)
async def create_complaint(
    background: BackgroundTasks,
    text: str = Form(default=""),
    ui_language: str = Form(default="en"),
    channel: str = Form(default="text"),
    lat: float | None = Form(default=None),
    lon: float | None = Form(default=None),
    location_text: str = Form(default=""),
    location_source: str = Form(default="unknown"),
    consent_exif_gps: bool = Form(default=False),
    device_ref: str = Form(default=""),
    photo: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Accept one complaint, triage it, and answer the citizen immediately."""
    text = (text or "").strip()[:MAX_TEXT_LENGTH]
    has_photo = photo is not None and bool(photo.filename)

    if not text and not has_photo:
        raise HTTPException(
            status_code=422,
            detail="Please describe the problem, or attach a photo, so we can act on it.",
        )

    image_intake = None
    if has_photo:
        raw = await photo.read()
        image_intake = image_stage.process_upload(
            raw,
            filename=photo.filename or "",
            consent_exif_gps=consent_exif_gps,
        )

    report = Report(
        ticket_code=new_ticket_code(),
        channel=channel if channel in {"text", "voice", "photo"} else "text",
        ui_language=ui_language[:12],
        raw_text_encrypted=encrypt_text(text),
        location_text=(location_text or "").strip()[:300],
        lat=lat,
        lon=lon,
        location_source=location_source if location_source in {"gps", "pin"} else "unknown",
        reporter_ref=hash_reference(device_ref),
        created_at=datetime.now(timezone.utc),
    )
    db.add(report)
    db.flush()

    try:
        outcome = run_pipeline(db, report, raw_text=text, image_intake=image_intake)
        db.commit()
    except Exception:
        # The report row itself is the citizen's receipt. If triage blew up we
        # still keep the complaint and hand it to a human, we never 500 a
        # citizen who did nothing wrong.
        logger.exception("Pipeline failed for report %s", report.ticket_code)
        db.rollback()
        report.pipeline_status = "failed"
        report.needs_review = True
        report.review_reason = "Automatic triage failed; queued for manual handling"
        db.add(report)
        db.commit()
        return {
            "ticket_code": report.ticket_code,
            "status": "received",
            "citizen_message": (
                "Your complaint has been registered. Our automatic triage could not run, "
                "so a municipal officer will handle it personally."
            ),
            "needs_review": True,
            "degraded": True,
        }

    issue = outcome.issue
    background.add_task(_rescore_cluster, issue.id)

    return {
        "ticket_code": report.ticket_code,
        "issue_code": issue.issue_code,
        "status": issue.status,
        "status_label": STATUS_LABELS_EN.get(issue.status, issue.status),
        "citizen_message": outcome.citizen_message,
        "category": category_block(issue.category),
        "sub_issue": report.sub_issue,
        "severity": report.severity,
        "hazard_flags": hazard_blocks(report.hazard_flags),
        "summary_en": report.summary_en,
        "ai": {
            "confidence": report.confidence,
            "source": report.ai_source,
            "model": report.ai_model,
            "explanation": report.ai_explanation,
            "matched_terms": (report.matched_terms or [])[:8],
        },
        "location": {
            "lat": report.lat,
            "lon": report.lon,
            "text": report.location_text,
            "source": report.location_source,
            "confidence": report.location_confidence,
            "ward": issue.ward.name if issue.ward is not None else None,
        },
        "cluster": {
            "joined_existing": outcome.joined_existing,
            "report_count": issue.report_count,
            "others": max(0, issue.report_count - 1),
        },
        "priority": {
            "score": issue.priority_score,
            "band": issue.priority_band,
            "breakdown": issue.priority_breakdown,
        },
        "sla": sla_block(issue),
        "department": issue.department,
        "redaction": report.redaction_summary or {},
        "review": {"needed": bool(outcome.review_kinds), "kinds": outcome.review_kinds},
        "image_url": f"/media/{report.image_path}" if report.image_path else None,
        "pipeline_ms": report.pipeline_ms,
    }


def _load_report(db: Session, ticket_code: str) -> Report:
    report = db.execute(
        select(Report).where(Report.ticket_code == ticket_code.strip().upper())
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail="We could not find that ticket number.")
    return report


@router.get("/complaints/{ticket_code}")
def track_complaint(ticket_code: str, db: Session = Depends(get_db)) -> dict:
    """Public tracking view for one ticket."""
    report = _load_report(db, ticket_code)
    issue = db.get(Issue, report.issue_id) if report.issue_id else None

    timeline: list[dict] = []
    feedback_given = False
    if issue is not None:
        events = db.execute(
            select(StatusEvent)
            .where(StatusEvent.issue_id == issue.id)
            .order_by(StatusEvent.created_at.asc())
        ).scalars().all()
        timeline = [status_event(event) for event in events]
        feedback_given = (
            db.execute(
                select(Feedback).where(Feedback.ticket_code == report.ticket_code)
            ).scalar_one_or_none()
            is not None
        )

    return {
        "report": report_public(report),
        "issue": issue_summary(issue) if issue is not None else None,
        "timeline": timeline,
        "priority_breakdown": issue.priority_breakdown if issue is not None else [],
        "can_give_feedback": bool(
            issue is not None and issue.status == "resolved" and not feedback_given
        ),
        "feedback_given": feedback_given,
        "pipeline_status": report.pipeline_status,
    }


@router.post("/complaints/{ticket_code}/feedback", status_code=201)
def submit_feedback(
    ticket_code: str, payload: FeedbackIn, db: Session = Depends(get_db)
) -> dict:
    """Close the loop: let the citizen rate the fix."""
    report = _load_report(db, ticket_code)
    if report.issue_id is None:
        raise HTTPException(status_code=409, detail="This complaint has not been triaged yet.")

    issue = db.get(Issue, report.issue_id)
    if issue is None or issue.status != "resolved":
        raise HTTPException(
            status_code=409,
            detail="You can rate this once the issue has been marked resolved.",
        )

    existing = db.execute(
        select(Feedback).where(Feedback.ticket_code == report.ticket_code)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="You have already rated this fix.")

    db.add(
        Feedback(
            issue_id=issue.id,
            report_id=report.id,
            ticket_code=report.ticket_code,
            rating=payload.rating,
            resolved_well=payload.rating >= 3,
            comment=payload.comment.strip()[:600],
        )
    )
    db.commit()
    return {"ok": True, "message": "Thank you - your rating helps hold the department to account."}
