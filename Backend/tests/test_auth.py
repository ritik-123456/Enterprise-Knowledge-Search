from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings

client = TestClient(app)


def test_auth_config_endpoint():
    """Verify public auth configuration endpoint returns client_id and does NOT expose secret."""
    resp = client.get("/api/auth/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_configured"] is True
    assert "apps.googleusercontent.com" in data["client_id"]
    # Verify client secret is strictly NOT in the response
    assert "client_secret" not in data
    assert "secret" not in data


def test_google_auth_missing_credential():
    """Verify empty or missing credential returns 400 Bad Request."""
    resp = client.post("/api/auth/google", json={"credential": ""})
    assert resp.status_code == 400


def test_google_auth_invalid_token():
    """Verify invalid token rejected by Google tokeninfo returns 401 Unauthorized."""
    resp = client.post("/api/auth/google", json={"credential": "invalid_fake_token_12345"})
    assert resp.status_code in (401, 503)


def test_google_auth_successful_verification():
    """Verify successful token verification with mocked Google response."""
    mock_token_info = {
        "sub": "109876543210987654321",
        "email": "developer@acme.com",
        "name": "Jane Doe",
        "picture": "https://lh3.googleusercontent.com/a/sample_avatar",
        "aud": settings.GOOGLE_CLIENT_ID,
        "iss": "https://accounts.google.com",
        "email_verified": "true"
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_token_info

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        resp = client.post(
            "/api/auth/google",
            json={"credential": "valid_mock_google_id_token"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["user"]["email"] == "developer@acme.com"
        assert data["user"]["name"] == "Jane Doe"
        assert data["user"]["picture"] == "https://lh3.googleusercontent.com/a/sample_avatar"
        assert "eks_sess_" in data["token"]


def test_logout_endpoint():
    """Verify logout returns 200."""
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
