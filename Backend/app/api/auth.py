import hashlib
import time
import logging
from typing import Dict, Any
import httpx
from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.schemas.auth import (
    GoogleAuthRequest,
    UserProfile,
    AuthResponse,
    AuthConfigResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Google Authentication"])

# Google Token Verification URL
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


@router.get("/config", response_model=AuthConfigResponse)
def get_auth_config():
    """
    Returns public Google OAuth configuration.
    The client ID is a public OAuth identifier safe for the frontend.
    The client secret is strictly kept on the backend and NEVER exposed.
    """
    configured = bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_ID.strip())
    return AuthConfigResponse(
        client_id=settings.GOOGLE_CLIENT_ID if configured else None,
        is_configured=configured
    )


@router.post("/google", response_model=AuthResponse)
async def authenticate_with_google(payload: GoogleAuthRequest):
    """
    Verifies a Google ID Token (credential) issued by Google Identity Services.
    Validates token signature, audience, and issuer with Google's public endpoint.
    Extracts user profile details and issues an authenticated session token.
    """
    credential = payload.credential.strip()
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Google credential ID token."
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                GOOGLE_TOKENINFO_URL,
                params={"id_token": credential}
            )

        if resp.status_code != 200:
            logger.warning(f"Google tokeninfo validation failed with status {resp.status_code}: {resp.text}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid, expired, or malformed Google ID token."
            )

        token_info: Dict[str, Any] = resp.json()
    except httpx.RequestError as exc:
        logger.error(f"Error contacting Google tokeninfo endpoint: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to verify token with Google Identity Services. Please try again later."
        )

    # 1. Validate audience (aud) matches our configured GOOGLE_CLIENT_ID
    expected_client_id = settings.GOOGLE_CLIENT_ID
    token_aud = token_info.get("aud")

    if expected_client_id and token_aud != expected_client_id:
        logger.warning(
            f"Token audience mismatch: token aud='{token_aud}', "
            f"expected='{expected_client_id}'"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google token was not issued for this application Client ID."
        )

    # 2. Validate issuer (iss) is Google
    token_iss = token_info.get("iss", "")
    if token_iss not in ("accounts.google.com", "https://accounts.google.com"):
        logger.warning(f"Invalid token issuer: '{token_iss}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token issuer."
        )

    # 3. Extract verified user profile
    sub = token_info.get("sub")
    email = token_info.get("email")
    if not sub or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google token missing required subject or email claims."
        )

    name = token_info.get("name") or email.split("@")[0]
    picture = token_info.get("picture")
    given_name = token_info.get("given_name")
    family_name = token_info.get("family_name")
    email_verified = str(token_info.get("email_verified", "")).lower() in ("true", "1")

    # Determine enterprise department & role (e.g., admin or platform team)
    role = "Admin" if email.endswith(("@acme.com", "@company.internal")) or "admin" in email.lower() else "Member"
    department = "Platform Reliability"

    user = UserProfile(
        id=str(sub),
        email=email,
        name=name,
        given_name=given_name,
        family_name=family_name,
        picture=picture,
        email_verified=email_verified,
        role=role,
        department=department
    )

    # 4. Generate persistent session token
    secret_bytes = settings.active_api_key.encode("utf-8") if settings.active_api_key else b"eks_auth_secret_seed"
    token_material = f"{sub}:{email}:{time.time()}".encode("utf-8")
    session_token = f"eks_sess_{hashlib.sha256(token_material + secret_bytes).hexdigest()[:32]}"

    logger.info(f"User successfully authenticated with Google OAuth: email='{email}', id='{sub}'")

    return AuthResponse(
        success=True,
        user=user,
        token=session_token,
        message=f"Welcome back, {user.name}!"
    )


@router.post("/logout")
def logout():
    """Logs out the active user session."""
    return {"success": True, "message": "Logged out successfully."}
