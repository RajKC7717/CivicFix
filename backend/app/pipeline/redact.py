"""PII redaction - stage 1 of the pipeline, and the privacy boundary.

Nothing downstream ever sees the citizen's raw text. The orchestrator encrypts
the original, keeps it in the local database, and passes only the redacted copy
to the classifier, the embedder, the logs and any external model.

The patterns target the identifiers that actually show up in Indian civic
complaints: mobile numbers, e-mail addresses, Aadhaar numbers, vehicle
registrations and PAN. Order matters - the 12-digit Aadhaar pattern must run
before the 10-digit phone pattern or a phone rule would eat part of an Aadhaar.

Deliberately NOT redacted: 6-digit PIN codes and house/plot numbers. They are
location signal, not identity, and removing them would make the complaint
unusable for the very purpose the citizen filed it.

This is a pattern-based safety net, not a guarantee. Free text can always carry
identity in ways regular expressions miss (see docs/LIMITATIONS.md), which is
why the raw text is encrypted at rest as a second line of defence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class RedactionResult:
    """Outcome of redacting one complaint."""

    text: str
    counts: dict[str, int] = field(default_factory=dict)
    #: Human-readable note shown to the citizen and in the officer's detail view.
    notice: str = ""

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def found_any(self) -> bool:
        return self.total > 0


#: (label, placeholder, compiled pattern). Evaluated in this exact order.
_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "email",
        "[EMAIL]",
        re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b", re.IGNORECASE),
    ),
    (
        "aadhaar",
        "[ID-NUMBER]",
        # 12 digits, first digit 2-9 (UIDAI never issues 0/1 as the first digit),
        # optionally grouped 4-4-4.
        re.compile(r"(?<!\d)[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}(?!\d)"),
    ),
    (
        "vehicle",
        "[VEHICLE]",
        # MH12AB1234 / MH 12 AB 1234 / MH-12-AB-1234
        re.compile(r"\b[A-Z]{2}[\s-]?\d{1,2}[\s-]?[A-Z]{1,3}[\s-]?\d{4}\b", re.IGNORECASE),
    ),
    (
        "pan",
        "[PAN]",
        re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    ),
    (
        "phone",
        "[PHONE]",
        # Indian mobile: optional +91 / 0 trunk prefix, then 10 digits starting 6-9.
        # The digit-boundary lookarounds sit on the OUTSIDE of the prefix group,
        # so a leading 0 is consumed by the prefix instead of blocking the match.
        re.compile(r"(?<!\d)(?:\+?91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)"),
    ),
)

_LABELS = {
    "email": "e-mail address",
    "aadhaar": "ID number",
    "vehicle": "vehicle number",
    "pan": "PAN",
    "phone": "phone number",
}


def redact(text: str) -> RedactionResult:
    """Mask personal identifiers in ``text``.

    Returns the redacted string plus a per-category count, so the UI can tell
    the citizen exactly what was removed instead of silently altering what they
    wrote.
    """
    if not text:
        return RedactionResult(text="")

    counts: dict[str, int] = {}
    redacted = text
    for label, placeholder, pattern in _RULES:
        redacted, hits = pattern.subn(placeholder, redacted)
        if hits:
            counts[label] = counts.get(label, 0) + hits

    notice = ""
    if counts:
        parts = [
            f"{count} {_LABELS[label]}{'s' if count > 1 else ''}"
            for label, count in counts.items()
        ]
        notice = "Removed before processing: " + ", ".join(parts)

    return RedactionResult(text=redacted, counts=counts, notice=notice)


def contains_pii(text: str) -> bool:
    """Cheap check used by tests and by the log filter."""
    return redact(text).found_any
