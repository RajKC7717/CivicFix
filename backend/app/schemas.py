"""Pydantic request/response models and the ORM -> dict builders.

Two rules run through this file:

* The citizen-facing shapes never expose raw complaint text, a reporter
  reference, or anything else that could identify a person. Only the redacted
  copy leaves the process.
* Every AI-produced field travels with its ``confidence`` and its ``source``, so
  the UI can always say *who* decided something - Claude, the offline
  classifier, or a named officer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.config.categories import (
    CATEGORY_BY_KEY,
    HAZARD_BY_KEY,
    ISSUE_STATUSES,
    LANGUAGE_LABELS,
    STATUS_LABELS_EN,
)
from app.models import AuditLog, Issue, PipelineStageLog, Report, ReviewTask, StatusEvent


# ---------------------------------------------------------------------------
#  Requests
# ---------------------------------------------------------------------------
class FeedbackIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=600)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=120)


class ReasonedAction(BaseModel):
    """Base for any officer action that overrides the AI.

    ``reason`` is required and must be substantive. An override without an
    explanation is indistinguishable from a mis-click, and the audit trail would
    be worthless.
    """

    reason: str = Field(min_length=8, max_length=500)

    @field_validator("reason")
    @classmethod
    def _meaningful(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 8:
            raise ValueError("Please give a short reason (at least 8 characters)")
        return cleaned


class CategoryOverrideIn(ReasonedAction):
    category: str


class PriorityOverrideIn(ReasonedAction):
    band: Literal["P1", "P2", "P3", "P4"] | None = None


class StatusChangeIn(BaseModel):
    status: str
    note: str = Field(default="", max_length=500)

    @field_validator("status")
    @classmethod
    def _known(cls, value: str) -> str:
        if value not in ISSUE_STATUSES:
            raise ValueError(f"status must be one of {ISSUE_STATUSES}")
        return value


class AssignIn(BaseModel):
    department: str
    assigned_to: str = Field(default="", max_length=80)
    note: str = Field(default="", max_length=500)


class MergeIn(ReasonedAction):
    target_issue_code: str


class ReviewResolveIn(ReasonedAction):
    """How an officer closed a review task."""

    action: Literal["confirm", "recategorise", "set_location", "merge", "keep_separate"]
    category: str | None = None
    lat: float | None = None
    lon: float | None = None
    location_text: str | None = Field(default=None, max_length=300)


class SettingsIn(BaseModel):
    equity_boost_enabled: bool | None = None
    reason: str = Field(default="", max_length=300)


# ---------------------------------------------------------------------------
#  Builders
# ---------------------------------------------------------------------------
def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def category_block(key: str | None, language: str = "en") -> dict[str, Any]:
    """Category with localised labels and its owning department."""
    category = CATEGORY_BY_KEY.get(key or "other", CATEGORY_BY_KEY["other"])
    return {
        "key": category.key,
        "label": category.label_en,
        "label_hi": category.label_hi,
        "label_mr": category.label_mr,
        "icon": category.icon,
        "department": category.department,
    }


def hazard_blocks(flags: list[str] | None) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for flag in flags or []:
        hazard = HAZARD_BY_KEY.get(flag)
        output.append(
            {
                "key": flag,
                "label": hazard.label_en if hazard else flag.replace("_", " ").title(),
                "label_hi": hazard.label_hi if hazard else "",
                "label_mr": hazard.label_mr if hazard else "",
            }
        )
    return output


def sla_block(issue: Issue) -> dict[str, Any]:
    return {
        "hours": issue.sla_hours,
        "deadline": _iso(issue.sla_deadline),
        "breached": bool(issue.sla_breached),
    }


def issue_summary(issue: Issue) -> dict[str, Any]:
    """Compact issue shape for lists, maps and queues."""
    return {
        "id": issue.id,
        "issue_code": issue.issue_code,
        "title": issue.title,
        "category": category_block(issue.category),
        "sub_issue": issue.sub_issue,
        "status": issue.status,
        "status_label": STATUS_LABELS_EN.get(issue.status, issue.status),
        "lat": issue.lat,
        "lon": issue.lon,
        "location_text": issue.location_text,
        "ward": (
            {"code": issue.ward.code, "name": issue.ward.name, "zone": issue.ward.zone}
            if issue.ward is not None
            else None
        ),
        "report_count": issue.report_count,
        "severity": issue.severity,
        "hazard_flags": hazard_blocks(issue.hazard_flags),
        "languages": [
            {"code": code, "label": LANGUAGE_LABELS.get(code, code)}
            for code in (issue.languages or [])
        ],
        "priority": {
            "score": issue.priority_score,
            "band": issue.priority_band,
            "overridden": bool(issue.priority_override_band),
            "equity_boost_applied": bool(issue.equity_boost_applied),
        },
        "sla": sla_block(issue),
        "department": issue.department,
        "assigned_to": issue.assigned_to,
        "created_at": _iso(issue.created_at),
        "updated_at": _iso(issue.updated_at),
        "resolved_at": _iso(issue.resolved_at),
    }


def report_public(report: Report) -> dict[str, Any]:
    """What a citizen or an officer may see of one report.

    Note what is absent: ``raw_text_encrypted`` and ``reporter_ref`` never
    appear in any API response.
    """
    return {
        "id": report.id,
        "ticket_code": report.ticket_code,
        "text": report.redacted_text,
        "summary_en": report.summary_en,
        "language": {
            "code": report.language,
            "label": LANGUAGE_LABELS.get(report.language, report.language),
            "confidence": report.language_confidence,
        },
        "channel": report.channel,
        "category": category_block(report.category),
        "severity": report.severity,
        "hazard_flags": hazard_blocks(report.hazard_flags),
        "ai": {
            "confidence": report.confidence,
            "source": report.ai_source,
            "model": report.ai_model,
            "explanation": report.ai_explanation,
            "matched_terms": report.matched_terms or [],
        },
        "location": {
            "lat": report.lat,
            "lon": report.lon,
            "text": report.location_text,
            "source": report.location_source,
            "confidence": report.location_confidence,
        },
        "image_url": f"/media/{report.image_path}" if report.image_path else None,
        "image_analysed": report.image_analysed,
        "dedup": {
            "decision": report.dedup_decision,
            "score": report.dedup_score,
            "detail": report.dedup_detail or {},
        },
        "redaction": report.redaction_summary or {},
        "needs_review": report.needs_review,
        "review_reason": report.review_reason,
        "created_at": _iso(report.created_at),
        "pipeline_ms": report.pipeline_ms,
    }


def status_event(event: StatusEvent) -> dict[str, Any]:
    return {
        "from_status": event.from_status,
        "to_status": event.to_status,
        "to_label": STATUS_LABELS_EN.get(event.to_status, event.to_status),
        "actor": event.actor,
        "actor_role": event.actor_role,
        "note": event.note,
        "created_at": _iso(event.created_at),
    }


def stage_log(log: PipelineStageLog) -> dict[str, Any]:
    return {
        "stage": log.stage,
        "status": log.status,
        "source": log.source,
        "confidence": log.confidence,
        "output": log.output,
        "message": log.message,
        "duration_ms": log.duration_ms,
        "created_at": _iso(log.created_at),
    }


def audit_entry(entry: AuditLog) -> dict[str, Any]:
    return {
        "id": entry.id,
        "actor": entry.actor,
        "actor_role": entry.actor_role,
        "action": entry.action,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "before": entry.before,
        "after": entry.after,
        "reason": entry.reason,
        "created_at": _iso(entry.created_at),
    }


def review_task(task: ReviewTask, *, report: Report | None = None) -> dict[str, Any]:
    return {
        "id": task.id,
        "kind": task.kind,
        "status": task.status,
        "payload": task.payload or {},
        "report_id": task.report_id,
        "issue_id": task.issue_id,
        "candidate_issue_id": task.candidate_issue_id,
        "report": report_public(report) if report is not None else None,
        "resolved_by": task.resolved_by,
        "resolved_at": _iso(task.resolved_at),
        "reason": task.reason,
        "resolution": task.resolution or {},
        "created_at": _iso(task.created_at),
    }
