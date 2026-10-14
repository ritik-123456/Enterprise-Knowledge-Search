from typing import Optional
from pydantic import BaseModel, Field


class GoogleAuthRequest(BaseModel):
    """Payload containing Google ID Token issued by Google Identity Services."""
    credential: str = Field(..., description="Google ID token (JWT) returned from Google Sign-In")


class UserProfile(BaseModel):
    """Authenticated user profile model."""
    id: str = Field(..., description="Unique Google subject identifier (sub)")
    email: str = Field(..., description="User's verified email address")
    name: str = Field(..., description="Full user display name")
    given_name: Optional[str] = Field(default=None, description="First name")
    family_name: Optional[str] = Field(default=None, description="Last name")
    picture: Optional[str] = Field(default=None, description="Google profile picture URL")
    email_verified: bool = Field(default=True, description="Email verification status from Google")
    role: str = Field(default="Member", description="Enterprise role: Admin, Member, or Viewer")
    department: str = Field(default="Platform Team", description="Assigned organizational department")


class AuthResponse(BaseModel):
    """Response returned upon successful authentication."""
    success: bool = Field(default=True, description="Authentication status flag")
    user: UserProfile = Field(..., description="Authenticated user profile details")
    token: str = Field(..., description="Session / authorization bearer token")
    message: str = Field(default="Authentication successful", description="Status message")


class AuthConfigResponse(BaseModel):
    """Public authentication configuration metadata for frontend initialization."""
    client_id: Optional[str] = Field(default=None, description="Google OAuth 2.0 public client ID")
    is_configured: bool = Field(default=False, description="Flag indicating if Google OAuth is enabled")
