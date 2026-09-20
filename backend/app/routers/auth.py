"""Officer authentication.

DEMO-GRADE ONLY, and labelled as such in the UI. A real deployment would
federate to the municipal corporation's identity provider; a hackathon
prototype that pretended to have done so would be making a security claim it
cannot support (docs/LIMITATIONS.md).

What is real: the token is HMAC-signed and expiring, the password compare is
constant-time, and every officer action is attributed to the named account in
the audit log.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.schemas import LoginIn
from app.security import AuthError, Officer, authenticate, issue_token, verify_token

router = APIRouter(prefix="/api/auth", tags=["auth"])
_scheme = HTTPBearer(auto_error=False)


def current_officer(
    credentials: HTTPAuthorizationCredentials | None = Depends(_scheme),
) -> Officer:
    """FastAPI dependency: resolve the bearer token to an officer."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to use the officer dashboard",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return verify_token(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@router.post("/login")
def login(payload: LoginIn) -> dict:
    """Exchange demo credentials for a bearer token."""
    try:
        officer = authenticate(payload.username, payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return {
        "token": issue_token(officer),
        "officer": {
            "username": officer.username,
            "display_name": officer.display_name,
            "role": officer.role,
            "department": officer.department,
        },
        "notice": "Demo credentials. Not a production authentication system.",
    }


@router.get("/me")
def me(officer: Officer = Depends(current_officer)) -> dict:
    return {
        "username": officer.username,
        "display_name": officer.display_name,
        "role": officer.role,
        "department": officer.department,
    }
