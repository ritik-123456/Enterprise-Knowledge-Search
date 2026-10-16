import time
import logging
from typing import Optional, Dict, Any

import jwt
import httpx
from fastapi import Request, HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)

GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
DEFAULT_TOKEN_EXPIRY_SECONDS = 30 * 24 * 60 * 60  # 30 days


def create_access_token(
    user_id: str,
    email: str,
    name: str = "",
    role: str = "Member",
    department: str = "Platform Team",
    expires_in_seconds: Optional[int] = None
) -> str:
    """
    Creates a cryptographically signed JWT session token for an authenticated user.
    """
    now = int(time.time())
    exp = now + (expires_in_seconds if expires_in_seconds is not None else DEFAULT_TOKEN_EXPIRY_SECONDS)
    payload = {
        "sub": str(user_id).strip(),
        "email": email.strip().lower() if email else "",
        "name": name,
        "role": role,
        "department": department,
        "iat": now,
        "exp": exp
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def verify_session_token(token: str) -> Dict[str, Any]:
    """
    Validates internal signed JWT session token.
    Raises jwt.ExpiredSignatureError if expired, or jwt.InvalidTokenError if invalid.
    """
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


async def verify_google_id_token(credential: str) -> Optional[Dict[str, Any]]:
    """
    Validates a raw Google ID Token via Google's tokeninfo endpoint as a fallback.
    """
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(
                GOOGLE_TOKENINFO_URL,
                params={"id_token": credential}
            )
        if resp.status_code != 200:
            return None
        info = resp.json()
        expected_client_id = settings.GOOGLE_CLIENT_ID
        if expected_client_id and info.get("aud") != expected_client_id:
            return None
        if info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
            return None
        if not info.get("sub"):
            return None
        return info
    except Exception as exc:
        logger.debug(f"Google ID token fallback verification failed: {exc}")
        return None


async def get_current_user_claims(request: Request) -> Dict[str, Any]:
    """
    Extracts and cryptographically validates user identity ONLY from the Authorization header.
    
    SECURITY INVARIANTS:
    1. NEVER inspects or honors X-User-Id, body fields, or query parameters.
    2. Missing, empty, malformed, forged, or expired tokens ALWAYS raise HTTP 401.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in with Google.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = auth_header.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is missing.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Decode and verify internal cryptographically signed JWT session token
    try:
        payload = verify_session_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication session has expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {err}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub = payload.get("sub")
    if not sub or not str(sub).strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload is missing or has empty subject claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


async def get_current_user_id(request: Request) -> str:
    """
    FastAPI dependency returning the verified user_id (string).
    Guaranteed to be non-empty and cryptographically verified.
    """
    claims = await get_current_user_claims(request)
    return str(claims["sub"]).strip()


async def get_current_user_email(request: Request) -> Optional[str]:
    """
    FastAPI dependency returning the verified user's email if available.
    """
    claims = await get_current_user_claims(request)
    return claims.get("email")
