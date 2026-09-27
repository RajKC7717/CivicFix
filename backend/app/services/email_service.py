"""Email drafting and sending service.

Generates professional complaint emails addressed to the relevant PMC
department, and optionally sends them via SMTP.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config.categories import CATEGORY_BY_KEY, HAZARD_BY_KEY
from app.config.department_contacts import CONTACT_BY_DEPARTMENT, DepartmentContact
from app.config.settings import settings
from app.models import EmailLog, Issue, Report

logger = logging.getLogger(__name__)


def get_department_contact(department: str) -> DepartmentContact:
    """Look up the contact for a department code, falling back to central."""
    return CONTACT_BY_DEPARTMENT.get(department, CONTACT_BY_DEPARTMENT["central"])


def draft_complaint_email(
    report: Report,
    issue: Issue,
) -> dict:
    """Generate a professional complaint email draft.

    Returns a dict with subject, body, recipient info, and metadata.
    The body has a warm but firm civic tone with a human touch.
    """
    contact = get_department_contact(issue.department)
    category = CATEGORY_BY_KEY.get(issue.category, CATEGORY_BY_KEY["other"])

    # Build hazard warning text
    hazard_lines = []
    for flag in (issue.hazard_flags or []):
        h = HAZARD_BY_KEY.get(flag)
        if h:
            hazard_lines.append(f"  ⚠ {h.label_en}")

    # Subject line
    location_part = issue.location_text or "Pune"
    subject = f"Civic Complaint: {category.label_en} at {location_part} — Ref: {report.ticket_code}"

    # Body
    body_parts = []
    body_parts.append(f"To,")
    body_parts.append(f"The {contact.designation},")
    body_parts.append(f"{contact.department_name},")
    body_parts.append(f"Pune Municipal Corporation")
    body_parts.append(f"{contact.office}")
    body_parts.append("")
    body_parts.append(f"Subject: {subject}")
    body_parts.append("")
    body_parts.append("Respected Sir/Madam,")
    body_parts.append("")
    body_parts.append(
        f"I am writing to bring to your kind attention a civic issue "
        f"that requires urgent action from your department. This complaint "
        f"has been registered through the NagarNetra citizen grievance portal "
        f"and is being formally escalated for your review."
    )
    body_parts.append("")
    body_parts.append("COMPLAINT DETAILS:")
    body_parts.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    body_parts.append(f"Reference No   : {report.ticket_code}")
    body_parts.append(f"Category       : {category.label_en}")
    body_parts.append(f"Severity       : {issue.severity}/5")
    body_parts.append(f"Priority Band  : {issue.priority_band} (Score: {round(issue.priority_score)}/100)")
    body_parts.append(f"Location       : {issue.location_text or 'See map on portal'}")
    if issue.ward:
        body_parts.append(f"Ward           : {issue.ward.name}")
    body_parts.append(f"Reported on    : {report.created_at.strftime('%d %B %Y, %I:%M %p') if report.created_at else 'N/A'}")
    if issue.sla_deadline:
        body_parts.append(f"SLA Deadline   : {issue.sla_deadline.strftime('%d %B %Y, %I:%M %p')}")
    body_parts.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    body_parts.append("")
    body_parts.append("DESCRIPTION:")
    body_parts.append(report.redacted_text or report.summary_en or "(See portal for details)")
    body_parts.append("")

    if hazard_lines:
        body_parts.append("HAZARD WARNINGS:")
        body_parts.extend(hazard_lines)
        body_parts.append("")

    if issue.report_count > 1:
        body_parts.append(
            f"CITIZEN IMPACT: This issue has been independently reported by "
            f"{issue.report_count} citizens, indicating a widespread concern "
            f"affecting multiple residents in the area."
        )
        body_parts.append("")

    body_parts.append(
        f"I humbly request you to kindly look into this matter at the "
        f"earliest convenience and take necessary corrective action. The "
        f"residents of this area have been facing considerable inconvenience "
        f"due to this issue."
    )
    body_parts.append("")
    body_parts.append(
        f"You can track the status of this complaint on the NagarNetra "
        f"portal using reference number: {report.ticket_code}"
    )
    body_parts.append("")
    body_parts.append("Thanking you in anticipation of a prompt response.")
    body_parts.append("")
    body_parts.append("Respectfully,")
    body_parts.append("A Concerned Citizen of Pune")
    body_parts.append("")
    body_parts.append("---")
    body_parts.append(f"This email was drafted via NagarNetra (नगरनेत्र) — PS-18 CivicFix")
    body_parts.append(f"Complaint Ref: {report.ticket_code}")

    body = "\n".join(body_parts)

    return {
        "subject": subject,
        "body": body,
        "recipient": {
            "email": contact.email,
            "department": contact.department_name,
            "designation": contact.designation,
            "office": contact.office,
            "phone": contact.phone,
        },
        "ticket_code": report.ticket_code,
        "note": "Department email addresses are publicly available from the Pune Municipal Corporation website.",
    }


def send_email(
    db: Session,
    *,
    report: Report,
    to_email: str,
    subject: str,
    body: str,
    citizen_email: str = "",
) -> dict:
    """Send a complaint email via SMTP or record it in demo mode."""
    log = EmailLog(
        report_id=report.id,
        ticket_code=report.ticket_code,
        to_email=to_email,
        from_email=settings.smtp_from_email,
        reply_to=citizen_email,
        subject=subject,
        body=body,
    )

    if not settings.smtp_enabled:
        log.status = "demo"
        db.add(log)
        db.commit()
        return {
            "ok": True,
            "status": "demo",
            "message": (
                "Email recorded in demo mode. In production, this would be "
                f"sent to {to_email} via SMTP."
            ),
        }

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
        msg["To"] = to_email
        if citizen_email:
            msg["Reply-To"] = citizen_email
        msg.set_content(body)

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)

        log.status = "sent"
        db.add(log)
        db.commit()
        return {"ok": True, "status": "sent", "message": f"Email sent successfully to {to_email}."}

    except Exception as exc:
        logger.exception("Failed to send email to %s", to_email)
        log.status = "failed"
        log.error_message = str(exc)[:500]
        db.add(log)
        db.commit()
        return {"ok": False, "status": "failed", "message": "Email could not be sent. Your complaint is still recorded and active."}
