"""The pipeline: one citizen report in, one triaged issue out.

    redact -> understand -> image -> geocode -> ward -> dedup -> priority -> sla

Every stage writes a :class:`PipelineStageLog` row recording what it produced,
how confident it was, which implementation answered (LLM, offline classifier,
cache, officer) and how long it took. That trace is what the officer's detail
view and the AI Health page are built from - without it, "explainable" would be
a slide rather than a feature.

Two invariants hold no matter what fails:

1. **Nothing is ever rejected.** A stage that fails degrades the record and
   usually raises a review task. It never discards a citizen's report.
2. **Nothing is ever deleted.** Deduplication links a report to an issue. The
   report keeps its own ticket code and stays independently addressable.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy.orm import Session

from app.config.categories import department_for_category
from app.config.policy import confidence_config
from app.models import Issue, PipelineStageLog, Report, ReviewTask, StatusEvent
from app.pipeline import dedup as dedup_stage
from app.pipeline import geocode as geocode_stage
from app.pipeline import image as image_stage
from app.pipeline import priority as priority_stage
from app.pipeline import sla as sla_stage
from app.pipeline import ward as ward_stage
from app.pipeline.redact import redact
from app.pipeline.types import Understanding
from app.pipeline.understand import understand
from app.security import new_issue_code
from app.services import equity as equity_service

logger = logging.getLogger(__name__)


@dataclass
class PipelineOutcome:
    """Everything the caller needs to answer the citizen."""

    report: Report
    issue: Issue | None = None
    understanding: Understanding | None = None
    dedup_decision: dedup_stage.DedupDecision | None = None
    priority: priority_stage.PriorityResult | None = None
    joined_existing: bool = False
    review_kinds: list[str] = field(default_factory=list)
    citizen_message: str = ""
    stage_summary: list[dict[str, Any]] = field(default_factory=list)


class _StageRecorder:
    """Times each stage and persists its trace."""

    def __init__(self, db: Session, report: Report) -> None:
        self.db = db
        self.report = report
        self.summary: list[dict[str, Any]] = []

    @contextmanager
    def stage(self, name: str) -> Iterator[dict[str, Any]]:
        """Context manager yielding a mutable record for one stage."""
        started = time.perf_counter()
        record: dict[str, Any] = {
            "status": "ok",
            "source": "",
            "confidence": None,
            "output": {},
            "message": "",
        }
        try:
            yield record
        except Exception as exc:  # noqa: BLE001 - a stage must never kill intake
            logger.exception("Pipeline stage %s failed for report %s", name, self.report.id)
            record["status"] = "error"
            record["message"] = f"{type(exc).__name__}: {exc}"[:500]
        finally:
            duration_ms = int((time.perf_counter() - started) * 1000)
            self.db.add(
                PipelineStageLog(
                    report_id=self.report.id,
                    stage=name,
                    status=record["status"],
                    source=str(record["source"])[:48],
                    confidence=record["confidence"],
                    output=record["output"],
                    message=str(record["message"])[:1000],
                    duration_ms=duration_ms,
                )
            )
            self.summary.append({"stage": name, "duration_ms": duration_ms, **record})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _raise_review(
    db: Session,
    report: Report,
    kind: str,
    payload: dict[str, Any],
    *,
    issue_id: int | None = None,
    candidate_issue_id: int | None = None,
) -> ReviewTask:
    """Queue work for a human. This is the only 'rejection' the system has."""
    task = ReviewTask(
        kind=kind,
        report_id=report.id,
        issue_id=issue_id,
        candidate_issue_id=candidate_issue_id,
        payload=payload,
        status="open",
    )
    db.add(task)
    report.needs_review = True
    report.review_reason = str(payload.get("summary", kind))[:200]
    return task


def _apply_report_to_issue(issue: Issue, report: Report, understanding: Understanding) -> None:
    """Fold a report's evidence into the issue it belongs to."""
    issue.report_count = (issue.report_count or 0) + 1
    issue.severity = max(int(issue.severity or 1), int(understanding.severity_1to5))

    hazards = list(issue.hazard_flags or [])
    for flag in understanding.hazard_flags:
        if flag not in hazards:
            hazards.append(flag)
    issue.hazard_flags = hazards

    languages = list(issue.languages or [])
    if report.language and report.language not in languages:
        languages.append(report.language)
    issue.languages = languages

    # A later report with a real pin upgrades an issue that had none.
    if issue.lat is None and report.lat is not None:
        issue.lat, issue.lon = report.lat, report.lon
        issue.ward_id = report.ward_id
    if not issue.location_text and report.location_text:
        issue.location_text = report.location_text[:300]
    # A cluster created from a vague first report can still acquire a match key
    # from a later, richer one - but it never overwrites an existing key.
    if not issue.match_text and report.match_text:
        issue.match_text = report.match_text
    issue.updated_at = _utcnow()


def refresh_issue_scoring(
    db: Session,
    issue: Issue,
    *,
    now: datetime | None = None,
    equity_enabled: bool | None = None,
) -> priority_stage.PriorityResult:
    """Recompute SLA and priority for one issue. Safe to call repeatedly."""
    now = now or _utcnow()

    assignment = sla_stage.assign_sla(issue.category, issue.hazard_flags or [], issue.created_at)
    issue.sla_hours = assignment.hours
    issue.sla_deadline = assignment.deadline
    state = sla_stage.evaluate_sla(
        hours=assignment.hours,
        created_at=issue.created_at,
        deadline=assignment.deadline,
        resolved_at=issue.resolved_at,
        now=now,
    )
    issue.sla_breached = state.breached

    # Acknowledgment window: when an officer should first view this issue
    if issue.ack_deadline is None:
        ack = sla_stage.assign_ack_window(
            issue.category, issue.hazard_flags or [], issue.created_at
        )
        issue.ack_window_hours = ack.window_hours
        issue.ack_deadline = ack.deadline

    underserved = equity_service.underserved_ward_codes(db)
    result = priority_stage.compute_priority(
        db,
        issue,
        now=now,
        underserved_wards=underserved,
        equity_enabled=equity_enabled,
    )
    issue.priority_score = result.score
    issue.priority_band = issue.priority_override_band or result.band
    issue.priority_breakdown = result.as_dict()
    issue.priority_computed_at = now
    issue.equity_boost_applied = result.equity_applied
    return result


def run_pipeline(
    db: Session,
    report: Report,
    *,
    raw_text: str,
    image_intake: image_stage.ImageIntake | None = None,
    equity_enabled: bool | None = None,
) -> PipelineOutcome:
    """Run every stage for one report and attach it to an issue."""
    recorder = _StageRecorder(db, report)
    outcome = PipelineOutcome(report=report)
    started = time.perf_counter()
    now = _utcnow()

    # ---------------- 1. redact ----------------
    redaction = redact(raw_text)
    with recorder.stage("redact") as record:
        report.redacted_text = redaction.text
        report.redaction_summary = {"counts": redaction.counts, "notice": redaction.notice}
        record["source"] = "regex-rules-v1"
        record["output"] = {"removed": redaction.counts}
        record["message"] = redaction.notice or "No personal identifiers found"

    # ---------------- 2. image ----------------
    image_b64 = image_media_type = None
    with recorder.stage("image") as record:
        if image_intake is None or not image_intake.accepted:
            record["status"] = "skipped"
            record["message"] = (
                image_intake.note if image_intake else "No photo attached"
            )
            record["output"] = {"analysed": False}
        else:
            report.image_path = image_intake.stored_path
            report.has_photo = True
            image_b64, image_media_type = image_stage.encode_for_llm(image_intake.stored_path)
            analysed = bool(image_b64)
            report.image_analysed = False  # set true below only if a model reads it
            record["source"] = "pillow"
            record["output"] = {
                "stored": True,
                "width": image_intake.width,
                "height": image_intake.height,
                "exif_stripped": image_intake.exif_stripped,
                "prepared_for_model": analysed,
            }
            record["message"] = image_intake.note

    # ---------------- 3. understand ----------------
    understanding = None
    with recorder.stage("understand") as record:
        understanding = understand(
            redaction.text,
            location_hint=report.location_text or "",
            image_b64=image_b64,
            image_media_type=image_media_type,
        )
        record["source"] = understanding.model or understanding.source
        record["confidence"] = understanding.confidence_0to1
        record["output"] = {
            "category": understanding.category,
            "severity": understanding.severity_1to5,
            "hazard_flags": understanding.hazard_flags,
            "language": understanding.language,
            "summary_en": understanding.summary_en,
            "matched_terms": understanding.matched_terms[:10],
        }
        record["message"] = understanding.explanation
        if understanding.source == "offline_classifier":
            record["status"] = "fallback"

    if understanding is None:  # only if the stage itself raised
        understanding = Understanding(
            category="other",
            language="unknown",
            summary_en="",
            confidence_0to1=0.0,
            source="unresolved",
            explanation="The understanding stage failed; this complaint needs a human.",
        )

    report.category = understanding.category
    report.sub_issue = understanding.sub_issue[:120]
    report.severity = understanding.severity_1to5
    report.hazard_flags = understanding.hazard_flags
    report.confidence = understanding.confidence_0to1
    report.ai_source = understanding.source
    report.ai_model = understanding.model[:64]
    report.ai_explanation = understanding.explanation
    report.matched_terms = understanding.matched_terms[:20]
    report.summary_en = understanding.summary_en
    report.match_text = understanding.match_text
    report.language = understanding.language
    if image_b64 and understanding.source == "llm":
        report.image_analysed = True
        report.image_findings = {"analysed_by": understanding.model}

    if not report.location_text and understanding.location_text:
        report.location_text = understanding.location_text[:300]

    # ---------------- 4. geocode ----------------
    resolution = geocode_stage.LocationResolution()
    with recorder.stage("geocode") as record:
        resolution = geocode_stage.resolve_location(
            db,
            lat=report.lat,
            lon=report.lon,
            coordinate_source=report.location_source or "gps",
            exif_lat=image_intake.exif_gps_lat if image_intake else None,
            exif_lon=image_intake.exif_gps_lon if image_intake else None,
            location_text=report.location_text or "",
            landmarks=understanding.landmarks,
        )
        report.lat, report.lon = resolution.lat, resolution.lon
        report.location_source = resolution.source
        report.location_confidence = resolution.confidence
        if resolution.display_name and not report.location_text:
            report.location_text = resolution.display_name[:300]
        record["source"] = resolution.source
        record["confidence"] = resolution.confidence
        record["output"] = {
            "lat": resolution.lat,
            "lon": resolution.lon,
            "display_name": resolution.display_name,
        }
        record["message"] = resolution.note or f"Located from {resolution.source}"
        if not resolution.resolved:
            record["status"] = "fallback"

    # ---------------- 5. ward ----------------
    with recorder.stage("ward") as record:
        hit = ward_stage.ward_for_point(report.lat, report.lon)
        if hit is None:
            record["status"] = "skipped"
            record["message"] = "No coordinate, so no ward could be assigned"
        else:
            report.ward_id = ward_stage.ward_id_for_point(db, report.lat, report.lon)
            record["source"] = hit.source
            record["output"] = {"ward_code": hit.code, "ward_name": hit.name}
            record["message"] = f"Assigned to {hit.name} ({hit.code})"

    # ---------------- 6. dedup ----------------
    decision = dedup_stage.DedupDecision(decision="new")
    with recorder.stage("dedup") as record:
        decision = dedup_stage.decide(
            db,
            category=understanding.category,
            match_text=understanding.match_text,
            lat=report.lat,
            lon=report.lon,
            created_at=report.created_at or now,
        )
        report.dedup_decision = decision.decision
        report.dedup_score = decision.score
        report.dedup_matched_issue_id = decision.issue.id if decision.issue else None
        report.dedup_detail = decision.as_dict()
        record["source"] = "embed+geo+time"
        record["confidence"] = decision.score
        record["output"] = decision.as_dict()
        record["message"] = decision.explanation

    # ---------------- attach to an issue ----------------
    joined = decision.decision == "merge" and decision.issue is not None
    if joined:
        issue = decision.issue
        _apply_report_to_issue(issue, report, understanding)
    else:
        issue = Issue(
            issue_code=new_issue_code(),
            title=(understanding.summary_en or report.redacted_text[:120] or "Untitled complaint"),
            match_text=understanding.match_text,
            category=understanding.category,
            sub_issue=understanding.sub_issue[:120],
            status="received",
            lat=report.lat,
            lon=report.lon,
            location_text=(report.location_text or "")[:300],
            ward_id=report.ward_id,
            report_count=1,
            severity=understanding.severity_1to5,
            hazard_flags=list(understanding.hazard_flags),
            languages=[report.language] if report.language else [],
            department=department_for_category(understanding.category),
            created_at=report.created_at or now,
        )
        db.add(issue)
        db.flush()
        db.add(
            StatusEvent(
                issue_id=issue.id,
                from_status=None,
                to_status="received",
                actor="system",
                actor_role="system",
                note="Complaint received and triaged automatically.",
            )
        )

    report.issue_id = issue.id
    db.flush()

    # ---------------- 7 + 8. priority and SLA ----------------
    with recorder.stage("priority") as record:
        result = refresh_issue_scoring(db, issue, now=now, equity_enabled=equity_enabled)
        outcome.priority = result
        record["source"] = "priority_config.yaml"
        record["output"] = {
            "score": result.score,
            "band": result.band,
            "breakdown": result.as_dict(),
        }
        record["message"] = result.headline

    with recorder.stage("sla") as record:
        hours, reason = sla_stage.sla_hours_for(issue.category, issue.hazard_flags or [])
        record["source"] = "priority_config.yaml"
        record["output"] = {
            "sla_hours": hours,
            "deadline": issue.sla_deadline.isoformat() if issue.sla_deadline else None,
            "breached": issue.sla_breached,
        }
        record["message"] = reason

    # ---------------- human-in-the-loop routing ----------------
    review_threshold = float(confidence_config()["review_category_below"])
    review_kinds: list[str] = []

    if understanding.confidence_0to1 <= 0.0 or not understanding.summary_en.strip():
        _raise_review(
            db,
            report,
            "unparsed",
            {
                "summary": "The AI could not understand this complaint",
                "text": report.redacted_text[:500],
                "category_guess": understanding.category,
            },
            issue_id=issue.id,
        )
        review_kinds.append("unparsed")
    elif understanding.confidence_0to1 < review_threshold:
        _raise_review(
            db,
            report,
            "low_confidence_category",
            {
                "summary": f"Low confidence ({understanding.confidence_0to1:.0%}) on "
                f"{understanding.category}",
                "text": report.redacted_text[:500],
                "category_guess": understanding.category,
                "confidence": understanding.confidence_0to1,
                "explanation": understanding.explanation,
            },
            issue_id=issue.id,
        )
        review_kinds.append("low_confidence_category")

    if decision.decision == "review" and decision.issue is not None:
        _raise_review(
            db,
            report,
            "duplicate_candidate",
            {
                "summary": f"Possible duplicate of {decision.issue.issue_code}",
                "explanation": decision.explanation,
                "score": decision.score,
                "candidate_code": decision.issue.issue_code,
                "candidate_title": decision.issue.title,
            },
            issue_id=issue.id,
            candidate_issue_id=decision.issue.id,
        )
        review_kinds.append("duplicate_candidate")

    if not resolution.resolved:
        _raise_review(
            db,
            report,
            "missing_location",
            {
                "summary": "Could not place this complaint on the map",
                "text": report.redacted_text[:500],
                "location_text": report.location_text,
                "note": resolution.note,
            },
            issue_id=issue.id,
        )
        review_kinds.append("missing_location")

    # ---------------- finish ----------------
    report.pipeline_status = "done"
    report.processed_at = now
    report.pipeline_ms = int((time.perf_counter() - started) * 1000)

    outcome.issue = issue
    outcome.understanding = understanding
    outcome.dedup_decision = decision
    outcome.joined_existing = joined
    outcome.review_kinds = review_kinds
    outcome.stage_summary = recorder.summary
    outcome.citizen_message = _citizen_message(joined, issue, review_kinds)
    return outcome


def _citizen_message(joined: bool, issue: Issue, review_kinds: list[str]) -> str:
    """The sentence the citizen sees. It never contains the word 'rejected'."""
    if joined:
        others = max(0, (issue.report_count or 1) - 1)
        if others == 1:
            return (
                "1 other person has reported this. Your report has been added to the same "
                "issue and has increased its priority."
            )
        return (
            f"{others} others have reported this. Your report has been added to the same "
            "issue and has increased its priority."
        )
    if "unparsed" in review_kinds:
        return (
            "Your complaint has been registered. Our system could not read it automatically, "
            "so a municipal officer will review it personally."
        )
    if "missing_location" in review_kinds:
        return (
            "Your complaint has been registered. We could not pinpoint the location, so an "
            "officer will confirm it on the map."
        )
    if "low_confidence_category" in review_kinds:
        return (
            "Your complaint has been registered. An officer will confirm the category before "
            "it is assigned."
        )
    return "Your complaint has been registered as a new issue and sent to the right department."
