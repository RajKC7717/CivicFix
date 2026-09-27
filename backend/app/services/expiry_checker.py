"""Background service to detect expired acknowledgment windows.

Runs periodically to find issues whose ack_deadline has passed without
an officer viewing them, and creates notifications for affected citizens.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.db import session_scope
from app.models import Issue, Notification, Report, StatusEvent

logger = logging.getLogger(__name__)


def check_expired_ack_windows() -> int:
    """Find issues past their ack_deadline and mark them expired.

    Returns the number of issues newly marked as expired.
    """
    db = session_scope()
    count = 0
    try:
        now = datetime.now(timezone.utc)
        expired_issues = (
            db.execute(
                select(Issue).where(
                    Issue.ack_status == "pending",
                    Issue.ack_deadline.isnot(None),
                    Issue.ack_deadline < now,
                    Issue.merged_into_id.is_(None),
                )
            )
            .scalars()
            .all()
        )

        for issue in expired_issues:
            issue.ack_status = "expired"

            # Create a status event noting the expiry
            db.add(
                StatusEvent(
                    issue_id=issue.id,
                    from_status=issue.status,
                    to_status=issue.status,  # status doesn't change, just a note
                    actor="system",
                    actor_role="system",
                    note=(
                        f"Acknowledgment window expired — no officer has reviewed "
                        f"this issue within the expected {issue.ack_window_hours} hours."
                    ),
                )
            )

            # Create notifications for all citizen tickets linked to this issue
            reports = (
                db.execute(select(Report).where(Report.issue_id == issue.id))
                .scalars()
                .all()
            )
            for report in reports:
                db.add(
                    Notification(
                        ticket_code=report.ticket_code,
                        issue_id=issue.id,
                        kind="ack_expired",
                        title="Your complaint has not been reviewed yet",
                        message=(
                            f"The expected review window of {issue.ack_window_hours} hours "
                            f"has passed and no officer has opened your complaint yet. "
                            f"Your complaint (Ref: {report.ticket_code}) remains active "
                            f"and has NOT been rejected. We are escalating this."
                        ),
                    )
                )
            count += 1

        if count:
            db.commit()
            logger.info("Marked %d issues as ack-expired", count)
        else:
            db.rollback()

    except Exception:
        logger.exception("Error checking expired ack windows")
        db.rollback()
    finally:
        db.close()

    return count


async def run_expiry_checker_loop(interval_seconds: int = 900) -> None:
    """Run the expiry checker every `interval_seconds` (default 15 minutes)."""
    logger.info("Expiry checker loop started (interval=%ds)", interval_seconds)
    while True:
        try:
            check_expired_ack_windows()
        except Exception:
            logger.exception("Expiry checker iteration failed")
        await asyncio.sleep(interval_seconds)
