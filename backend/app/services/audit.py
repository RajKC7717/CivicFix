"""Append-only audit trail for every human decision.

Design rule: if a person changed something the AI decided, there is a row here
with their name, the old value, the new value and their written reason. No code
path in NagarNetra updates or deletes a row in this table.

The reason is mandatory at the API layer, not optional-with-a-default. An
override with no explanation is indistinguishable from an accident, and the
whole point of the accountability story is that it cannot happen quietly.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog


def record(
    db: Session,
    *,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str | int,
    reason: str = "",
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    actor_role: str = "officer",
) -> AuditLog:
    """Write one audit entry. The caller still owns the transaction."""
    entry = AuditLog(
        actor=actor,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        before=before,
        after=after,
        reason=reason.strip(),
    )
    db.add(entry)
    db.flush()
    return entry


def recent(db: Session, *, limit: int = 100, offset: int = 0) -> list[AuditLog]:
    """Most recent entries first."""
    return list(
        db.execute(
            select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset(offset)
            .limit(limit)
        )
        .scalars()
        .all()
    )


def count_for(db: Session, entity_type: str, entity_id: str | int) -> int:
    rows = db.execute(
        select(AuditLog.id).where(
            AuditLog.entity_type == entity_type, AuditLog.entity_id == str(entity_id)
        )
    ).all()
    return len(rows)


def for_entity(db: Session, entity_type: str, entity_id: str | int) -> list[AuditLog]:
    """Full history for one issue or report, oldest first."""
    return list(
        db.execute(
            select(AuditLog)
            .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == str(entity_id))
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        )
        .scalars()
        .all()
    )
