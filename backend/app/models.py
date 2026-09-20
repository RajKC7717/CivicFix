"""SQLAlchemy ORM models.

Two ideas drive this schema:

1. A **Report** is what one citizen said. It is immutable evidence and is never
   deleted, never merged away, never rejected. Deduplication only ever *links* a
   report to an issue.
2. An **Issue** is what the city has to fix. It is the unit of work, of SLA, of
   assignment and of priority. One issue may carry many reports in many
   languages - that is the point.

Everything else here exists to make an AI decision reviewable after the fact:
per-stage logs, a review queue, and an append-only audit trail.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    """Timezone-aware UTC now (SQLite has no native tz support)."""
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# ---------------------------------------------------------------------------
#  Geography
# ---------------------------------------------------------------------------
class Ward(Base):
    """An administrative ward. Geometry lives in data/wards.geojson."""

    __tablename__ = "wards"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    zone: Mapped[str] = mapped_column(String(40), default="")
    population: Mapped[int] = mapped_column(Integer, default=0)
    area_sq_km: Mapped[float] = mapped_column(Float, default=0.0)
    centroid_lat: Mapped[float] = mapped_column(Float, default=0.0)
    centroid_lon: Mapped[float] = mapped_column(Float, default=0.0)

    issues: Mapped[list["Issue"]] = relationship(back_populates="ward")


class Poi(Base):
    """A point of interest that makes a nearby hazard worse (school, hospital)."""

    __tablename__ = "pois"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(24), index=True)  # school | hospital
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    ward_code: Mapped[str | None] = mapped_column(String(16), nullable=True)


class GeocodeCache(Base):
    """Cached Nominatim lookups.

    The Nominatim usage policy allows one request per second. Caching keeps the
    demo fast, keeps us inside that policy, and means a repeat demo works with
    no network at all.
    """

    __tablename__ = "geocode_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    query_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    query: Mapped[str] = mapped_column(String(512))
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    display_name: Mapped[str] = mapped_column(String(512), default="")
    source: Mapped[str] = mapped_column(String(32), default="nominatim")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------------------
#  Core: issues and reports
# ---------------------------------------------------------------------------
class Issue(Base, TimestampMixin):
    """A clustered real-world problem: the unit of municipal work."""

    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_code: Mapped[str] = mapped_column(String(24), unique=True, index=True)

    title: Mapped[str] = mapped_column(String(200), default="")
    category: Mapped[str] = mapped_column(String(48), index=True)
    sub_issue: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(24), default="received", index=True)

    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_text: Mapped[str] = mapped_column(String(300), default="")
    ward_id: Mapped[int | None] = mapped_column(ForeignKey("wards.id"), nullable=True, index=True)

    report_count: Mapped[int] = mapped_column(Integer, default=1, index=True)
    severity: Mapped[int] = mapped_column(Integer, default=3)
    hazard_flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    languages: Mapped[list[str]] = mapped_column(JSON, default=list)

    # --- explainable priority ---
    priority_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    priority_band: Mapped[str] = mapped_column(String(4), default="P4", index=True)
    priority_breakdown: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    priority_computed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    equity_boost_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    priority_override_band: Mapped[str | None] = mapped_column(String(4), nullable=True)
    priority_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- SLA ---
    sla_hours: Mapped[int] = mapped_column(Integer, default=96)
    sla_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sla_breached: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # --- routing ---
    department: Mapped[str] = mapped_column(String(32), default="central", index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(80), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str] = mapped_column(Text, default="")

    #: Only populated for seeded evaluation data; lets evaluate.py score dedup.
    ground_truth_cluster: Mapped[str | None] = mapped_column(String(48), nullable=True)

    ward: Mapped[Ward | None] = relationship(back_populates="issues")
    reports: Mapped[list["Report"]] = relationship(
        back_populates="issue", foreign_keys="Report.issue_id"
    )
    status_events: Mapped[list["StatusEvent"]] = relationship(
        back_populates="issue", cascade="all, delete-orphan", order_by="StatusEvent.created_at"
    )

    __table_args__ = (
        Index("ix_issues_cat_status", "category", "status"),
        Index("ix_issues_open_geo", "status", "lat", "lon"),
    )


class Report(Base):
    """One citizen submission. Immutable evidence - only ever linked, never removed."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    issue_id: Mapped[int | None] = mapped_column(ForeignKey("issues.id"), nullable=True, index=True)

    # --- intake ---
    channel: Mapped[str] = mapped_column(String(24), default="text")  # text|voice|photo
    has_photo: Mapped[bool] = mapped_column(Boolean, default=False)
    ui_language: Mapped[str] = mapped_column(String(12), default="en")
    #: Fernet ciphertext. The plaintext never leaves the process and never
    #: reaches a log, an LLM or the API surface.
    raw_text_encrypted: Mapped[str] = mapped_column(Text, default="")
    #: Redacted copy - this is the ONLY text an external model ever sees.
    redacted_text: Mapped[str] = mapped_column(Text, default="")
    redaction_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    summary_en: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(12), default="unknown", index=True)
    language_confidence: Mapped[float] = mapped_column(Float, default=0.0)

    # --- location ---
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_text: Mapped[str] = mapped_column(String(300), default="")
    location_source: Mapped[str] = mapped_column(String(24), default="unknown")
    location_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    ward_id: Mapped[int | None] = mapped_column(ForeignKey("wards.id"), nullable=True, index=True)

    # --- AI understanding ---
    category: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    sub_issue: Mapped[str] = mapped_column(String(120), default="")
    severity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hazard_flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    ai_source: Mapped[str] = mapped_column(String(32), default="unresolved", index=True)
    ai_model: Mapped[str] = mapped_column(String(64), default="")
    ai_explanation: Mapped[str] = mapped_column(Text, default="")
    matched_terms: Mapped[list[str]] = mapped_column(JSON, default=list)

    # --- image ---
    image_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    image_analysed: Mapped[bool] = mapped_column(Boolean, default=False)
    image_findings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # --- dedup ---
    dedup_decision: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    dedup_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    dedup_matched_issue_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dedup_detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # --- human-in-the-loop ---
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    review_reason: Mapped[str] = mapped_column(String(200), default="")

    # --- lifecycle ---
    pipeline_status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    pipeline_error: Mapped[str] = mapped_column(Text, default="")
    pipeline_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: Salted hash of a device/session id. Lets us count distinct citizens
    #: without storing anything that identifies one.
    reporter_ref: Mapped[str] = mapped_column(String(64), default="", index=True)
    #: Ground truth for evaluation runs only.
    ground_truth_category: Mapped[str | None] = mapped_column(String(48), nullable=True)
    ground_truth_cluster: Mapped[str | None] = mapped_column(String(48), nullable=True)
    is_seed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    issue: Mapped[Issue | None] = relationship(back_populates="reports", foreign_keys=[issue_id])
    stage_logs: Mapped[list["PipelineStageLog"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
#  Accountability
# ---------------------------------------------------------------------------
class StatusEvent(Base):
    """One transition on the public timeline."""

    __tablename__ = "status_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str] = mapped_column(String(24))
    actor: Mapped[str] = mapped_column(String(80), default="system")
    actor_role: Mapped[str] = mapped_column(String(24), default="system")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    issue: Mapped[Issue] = relationship(back_populates="status_events")


class ReviewTask(Base):
    """Human-in-the-loop work item. Nothing is auto-rejected; it lands here."""

    __tablename__ = "review_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    report_id: Mapped[int | None] = mapped_column(
        ForeignKey("reports.id"), nullable=True, index=True
    )
    issue_id: Mapped[int | None] = mapped_column(ForeignKey("issues.id"), nullable=True, index=True)
    candidate_issue_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)  # open|resolved
    resolution: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    resolved_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class AuditLog(Base):
    """Append-only record of every human override and every policy toggle.

    Nothing in the product deletes or edits rows in this table.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(80), index=True)
    actor_role: Mapped[str] = mapped_column(String(24), default="officer")
    action: Mapped[str] = mapped_column(String(48), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[str] = mapped_column(String(48), index=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class PipelineStageLog(Base):
    """Per-stage trace: what each AI stage produced, how sure it was, how long it took."""

    __tablename__ = "pipeline_stage_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), index=True)
    stage: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok|fallback|error|skipped
    source: Mapped[str] = mapped_column(String(48), default="")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    message: Mapped[str] = mapped_column(Text, default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    report: Mapped[Report] = relationship(back_populates="stage_logs")


class Feedback(Base):
    """Citizen rating of a completed fix - closes the loop."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"), index=True)
    report_id: Mapped[int | None] = mapped_column(ForeignKey("reports.id"), nullable=True)
    ticket_code: Mapped[str] = mapped_column(String(24), index=True)
    rating: Mapped[int] = mapped_column(Integer)  # 1..5
    resolved_well: Mapped[bool] = mapped_column(Boolean, default=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("ticket_code", name="uq_feedback_ticket"),)


class Setting(Base):
    """Runtime policy toggles that officers may flip from the UI."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    updated_by: Mapped[str] = mapped_column(String(80), default="system")


class EvalRun(Base):
    """A stored result from scripts/evaluate.py, surfaced on the AI Health page."""

    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(64), default="holdout")
    report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
