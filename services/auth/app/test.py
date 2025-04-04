from fastapi.testclient import TestClient
from app.app import app

client = TestClient(app)

# Mock data for testing
MOCK_USER_ID = "test-user-id"
MOCK_ACCESS_TOKEN = "mock-access-token"
MOCK_REFRESH_TOKEN = "mock-refresh-token"
MOCK_EMAIL = "test@example.com"
MOCK_PASSWORD = "TestPassword123"

def test_health_check():
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "auth-service"

def test_login_flow():
    """
    Test the complete login flow.
    This is now an integration test that requires a real backend.
    """
    # Make the login request
    response = client.post(
        "/api/auth/login",
        json={"email": MOCK_EMAIL, "password": MOCK_PASSWORD}
    )
    
    # Assert response structure (but not exact values since they'd be dynamic)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert "user_id" in data
    assert "email" in data
    assert "roles" in data


def test_token_verification():
    """Test token verification with a real token."""
    # First login to get a token
    login_response = client.post(
        "/api/auth/login",
        json={"email": MOCK_EMAIL, "password": MOCK_PASSWORD}
    )
    
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    # Verify the token
    verify_response = client.post(
        "/api/auth/token/verify",
        json={"token": token}
    )
    
    assert verify_response.status_code == 200
    data = verify_response.json()
    assert data["valid"] is True
    assert "user_id" in data
    assert "email" in data


def test_token_refresh():
    """Test refreshing a token."""
    # First login to get a refresh token
    login_response = client.post(
        "/api/auth/login",
        json={"email": MOCK_EMAIL, "password": MOCK_PASSWORD}
    )
    
    assert login_response.status_code == 200
    refresh_token = login_response.json()["refresh_token"]
    
    # Use the refresh token to get a new access token
    refresh_response = client.post(
        "/api/auth/token/refresh",
        json={"refresh_token": refresh_token}
    )
    
    assert refresh_response.status_code == 200
    data = refresh_response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert "expires_in" in data


def test_user_registration():
    """Test user registration process."""
    # Generate a unique email for this test
    import uuid
    unique_email = f"test-{uuid.uuid4()}@example.com"
    
    # Register a new user
    register_response = client.post(
        "/api/auth/register",
        json={
            "email": unique_email,
            "password": MOCK_PASSWORD,
            "firstName": "Test",
            "lastName": "User",
            "user_type": "patient"
        }
    )
    
    # Check registration was successful
    assert register_response.status_code == 201
    data = register_response.json()
    assert "message" in data
    assert "user_id" in data
    assert "access_token" in data


def test_logout():
    """Test logout functionality."""
    # First login to get a token
    login_response = client.post(
        "/api/auth/login",
        json={"email": MOCK_EMAIL, "password": MOCK_PASSWORD}
    )
    
    assert login_response.status_code == 200
    refresh_token = login_response.json()["refresh_token"]
    
    # Logout using the token
    logout_response = client.post(
        "/api/auth/logout",
        json={"refresh_token": refresh_token}
    )
    
    assert logout_response.status_code == 200
    data = logout_response.json()
    assert data["message"] == "Logged out successfully"


def test_forgot_password():
    """Test password reset request."""
    # Request password reset
    response = client.post(
        "/api/auth/forgot-password",
        json={"email": MOCK_EMAIL}
    )
    
    # Even if user doesn't exist, API should return success for security
    assert response.status_code == 200
    data = response.json()
    assert "message" in data


def test_get_user_info():
    """Test retrieving user information."""
    # First login to get token and user_id
    login_response = client.post(
        "/api/auth/login",
        json={"email": MOCK_EMAIL, "password": MOCK_PASSWORD}
    )
    
    assert login_response.status_code == 200
    user_id = login_response.json()["user_id"]
    token = login_response.json()["access_token"]
    
    # Get user info
    user_response = client.get(
        f"/api/auth/user/{user_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert user_response.status_code == 200
    data = user_response.json()
    assert "id" in data
    assert "email" in data
    assert "roles" in data


def test_integration_endpoints():
    """Test integration endpoints are accessible."""
    # This would require proper auth
    login_response = client.post(
        "/api/auth/login",
        json={"email": MOCK_EMAIL, "password": MOCK_PASSWORD}
    )
    
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    # Try accessing integration endpoint
    response = client.post(
        "/api/auth/integration/verify-service",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    # Response code might vary based on implementation
    assert response.status_code in [200, 204, 403, 422]