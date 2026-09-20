"""Encryption at rest, reference hashing, code generation and demo auth.

Privacy posture (see docs/RESPONSIBLE_AI.md):

* The citizen's **raw** complaint text is Fernet-encrypted before it is written
  to disk. Nothing in the API ever returns it.
* Only the **redacted** text is used for classification, logged, or sent to an
  external model.
* A reporter is tracked by a salted hash of a client-generated device id, so we
  can count distinct citizens without ever storing an identifier.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken

from app.config.settings import settings

# Crockford-style alphabet: no I, L, O, U - unambiguous when read aloud or
# written on a paper acknowledgement slip at a ward office.
_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


# ---------------------------------------------------------------------------
#  Encryption at rest
# ---------------------------------------------------------------------------
def _fernet() -> Fernet:
    """Derive a stable Fernet key from SECRET_KEY.

    Deterministic on purpose: the same .env decrypts an existing database. In a
    real deployment this key would come from a KMS, not from a derived secret.
    """
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_text(plaintext: str) -> str:
    """Encrypt citizen text for storage. Returns '' for empty input."""
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_text(ciphertext: str) -> str:
    """Decrypt stored citizen text.

    Returns an empty string rather than raising if the key has changed, so a
    rotated secret degrades the record instead of breaking the whole dashboard.
    """
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def hash_reference(value: str) -> str:
    """Salted, non-reversible reference for a device/session id."""
    if not value:
        return ""
    salted = f"{settings.secret_key}:{value}".encode("utf-8")
    return hashlib.sha256(salted).hexdigest()[:32]


# ---------------------------------------------------------------------------
#  Human-readable codes
# ---------------------------------------------------------------------------
def _random_code(length: int) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def new_ticket_code() -> str:
    """Citizen-facing ticket id, e.g. ``NN-7K3M92QP``."""
    return f"NN-{_random_code(8)}"


def new_issue_code() -> str:
    """Officer-facing issue id, e.g. ``ISU-4T8W21``."""
    return f"ISU-{_random_code(6)}"


# ---------------------------------------------------------------------------
#  Demo authentication
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Officer:
    username: str
    display_name: str
    role: str
    department: str


#: DEMO ONLY. A real deployment would federate to the corporation's directory.
#: Passwords are here in plaintext deliberately: hiding them would imply a
#: security property this prototype does not have. See docs/LIMITATIONS.md.
DEMO_OFFICERS: dict[str, tuple[str, Officer]] = {
    "officer": (
        "officer",
        Officer("officer", "A. Deshpande (Ward Officer)", "officer", "central"),
    ),
    "roads": (
        "roads",
        Officer("roads", "S. Kulkarni (Roads Dept)", "officer", "roads"),
    ),
    "commissioner": (
        "commissioner",
        Officer("commissioner", "Dr. M. Rane (Commissioner)", "admin", "central"),
    ),
}


class AuthError(Exception):
    """Raised for a bad credential or an invalid/expired token."""


def authenticate(username: str, password: str) -> Officer:
    """Validate demo credentials, constant-time on the password compare."""
    entry = DEMO_OFFICERS.get((username or "").strip().lower())
    if entry is None:
        # Still burn a compare so a wrong username is not obviously faster.
        hmac.compare_digest("x" * 16, "y" * 16)
        raise AuthError("Unknown username or password")
    expected, officer = entry
    if not hmac.compare_digest(expected, password or ""):
        raise AuthError("Unknown username or password")
    return officer


def _sign(payload: str) -> str:
    mac = hmac.new(settings.secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256)
    return base64.urlsafe_b64encode(mac.digest()).decode("ascii").rstrip("=")


def issue_token(officer: Officer) -> str:
    """Create a signed, expiring bearer token (HMAC-SHA256, no external dep)."""
    body = {
        "u": officer.username,
        "n": officer.display_name,
        "r": officer.role,
        "d": officer.department,
        "exp": int(time.time()) + settings.token_ttl_hours * 3600,
    }
    raw = base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode()).decode()
    raw = raw.rstrip("=")
    return f"{raw}.{_sign(raw)}"


def verify_token(token: str) -> Officer:
    """Verify a bearer token and return the officer it names."""
    try:
        raw, signature = (token or "").split(".", 1)
    except ValueError as exc:
        raise AuthError("Malformed token") from exc
    if not hmac.compare_digest(_sign(raw), signature):
        raise AuthError("Invalid token signature")
    padding = "=" * (-len(raw) % 4)
    try:
        body = json.loads(base64.urlsafe_b64decode(raw + padding))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthError("Malformed token payload") from exc
    if int(body.get("exp", 0)) < int(time.time()):
        raise AuthError("Session expired, please sign in again")
    return Officer(
        username=body.get("u", ""),
        display_name=body.get("n", ""),
        role=body.get("r", "officer"),
        department=body.get("d", "central"),
    )
