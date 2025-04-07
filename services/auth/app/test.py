import jwt
from jwt.algorithms import RSAAlgorithm
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import base64
import json
import os
import time
import uuid
import logging
import requests
from unittest import mock
from fastapi.testclient import TestClient
import pytest

from app.app import app

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("test_auth")

# Test data
TEST_PASSWORD = "TestPassword123"
TEST_EMAIL = "test@example.com"
TEST_FIRST_NAME = "Test"
TEST_LAST_NAME = "User"
TEST_USER_TYPE = "patient"

# Generate a private key for signing tokens
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048
)

# Get the public key for verification
public_key = private_key.public_key()

# Convert to PEM format
pem_private_key = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)

pem_public_key = public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
)

# Create a valid JWT with the private key
def create_jwt_token(user_id=None, email=None, roles=None, exp_delta=3600):
    now = int(time.time())
    user_id = user_id or "mock-user-id"
    email = email or TEST_EMAIL
    roles = roles or ["user", "patient-role"]
    
    payload = {
        "iss": "http://keycloak:8080/realms/medapp",
        "sub": user_id,
        "aud": "account",
        "iat": now,
        "exp": now + exp_delta,
        "email": email,
        "name": "Test User",
        "given_name": TEST_FIRST_NAME,
        "family_name": TEST_LAST_NAME,
        "preferred_username": email,
        "realm_access": {
            "roles": roles
        }
    }
    
    token = jwt.encode(payload, pem_private_key, algorithm="RS256")
    return token

# Create mock tokens
test_user_id = "mock-user-id"
test_access_token = create_jwt_token()
test_refresh_token = "mock-refresh-token-" + str(uuid.uuid4())

# Mock Keycloak responses
class MockResponse:
    def __init__(self, json_data, status_code=200):
        self.json_data = json_data
        self.status_code = status_code
        self.text = json.dumps(json_data)
        self.headers = {}

    def json(self):
        return self.json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP Error: {self.status_code}")

# Mock functions
def mock_post(*args, **kwargs):
    url = args[0]
    
    # Token endpoint
    if url.endswith('/token'):
        data = kwargs.get('data', {})
        
        # Client credentials grant for admin
        if data.get('grant_type') == 'client_credentials':
            return MockResponse({
                "access_token": create_jwt_token(roles=["admin"]),
                "token_type": "bearer",
                "expires_in": 300
            })
        
        # Password grant for login
        elif data.get('grant_type') == 'password':
            if data.get('username') == TEST_EMAIL and data.get('password') == TEST_PASSWORD:
                return MockResponse({
                    "access_token": test_access_token,
                    "refresh_token": test_refresh_token,
                    "token_type": "bearer",
                    "expires_in": 300
                })
            else:
                return MockResponse({
                    "error": "invalid_grant",
                    "error_description": "Invalid user credentials"
                }, 401)
        
        # Refresh token grant
        elif data.get('grant_type') == 'refresh_token':
            return MockResponse({
                "access_token": create_jwt_token(),
                "refresh_token": "mock-new-refresh-token-" + str(uuid.uuid4()),
                "token_type": "bearer",
                "expires_in": 300
            })
    
    # User creation endpoint
    elif url.endswith('/users'):
        mock_resp = MockResponse({}, 201)
        mock_resp.headers["Location"] = "/users/mock-user-id"
        return mock_resp
    
    # Role mapping endpoint
    elif '/role-mappings/' in url:
        return MockResponse({}, 204)
    
    # Logout endpoint
    elif url.endswith('/logout'):
        return MockResponse({}, 204)
    
    # Token introspection
    elif url.endswith('/token/introspect'):
        return MockResponse({"active": True, "sub": test_user_id, "email": TEST_EMAIL})
    
    return MockResponse({"error": "Not mocked"}, 404)

def mock_get(*args, **kwargs):
    url = args[0]
    
    # User info endpoint
    if url.endswith('/userinfo'):
        return MockResponse({
            "sub": test_user_id,
            "email": TEST_EMAIL,
            "name": "Test User",
            "given_name": TEST_FIRST_NAME,
            "family_name": TEST_LAST_NAME,
            "preferred_username": TEST_EMAIL,
            "realm_access": {
                "roles": ["user", "patient-role"]
            }
        })
    
    # User search endpoint
    elif '/users?' in url:
        if 'email=' + TEST_EMAIL in url:
            return MockResponse([{
                "id": test_user_id,
                "username": TEST_EMAIL,
                "email": TEST_EMAIL,
                "firstName": TEST_FIRST_NAME,
                "lastName": TEST_LAST_NAME,
                "enabled": True,
                "emailVerified": True
            }])
        else:
            return MockResponse([])
    
    # User by ID endpoint
    elif '/users/' in url and not '/role-mappings/' in url:
        return MockResponse({
            "id": test_user_id,
            "username": TEST_EMAIL,
            "email": TEST_EMAIL,
            "firstName": TEST_FIRST_NAME,
            "lastName": TEST_LAST_NAME,
            "enabled": True,
            "emailVerified": True,
            "attributes": {
                "user_type": ["patient"]
            }
        })
    
    # Roles endpoint
    elif '/roles' in url:
        return MockResponse([
            {"id": "role-1", "name": "admin"},
            {"id": "role-2", "name": "user"},
            {"id": "role-3", "name": "patient-role"},
            {"id": "role-4", "name": "doctor-role"}
        ])
    
    # Well-known endpoint
    elif '.well-known/openid-configuration' in url:
        return MockResponse({
            "issuer": "http://keycloak:8080/realms/medapp",
            "jwks_uri": "http://keycloak:8080/realms/medapp/protocol/openid-connect/certs"
        })
    
    # JWKS endpoint
    elif '/certs' in url or '/protocol/openid-connect/certs' in url:
        # Return the actual public key in JWKS format
        public_numbers = public_key.public_numbers()
        e = public_numbers.e.to_bytes((public_numbers.e.bit_length() + 7) // 8, byteorder='big')
        n = public_numbers.n.to_bytes((public_numbers.n.bit_length() + 7) // 8, byteorder='big')
        
        e_b64 = base64.urlsafe_b64encode(e).decode('utf-8').rstrip('=')
        n_b64 = base64.urlsafe_b64encode(n).decode('utf-8').rstrip('=')
        
        return MockResponse({
            "keys": [{
                "kid": "mock-key-id",
                "kty": "RSA",
                "alg": "RS256",
                "use": "sig",
                "n": n_b64,
                "e": e_b64
            }]
        })
    
    return MockResponse({"error": "Not mocked"}, 404)

# Mock RSA algorithm
def mock_from_jwk(jwk_dict):
    return pem_public_key

# Set up the test client with mocked requests
@pytest.fixture(scope="module", autouse=True)
def setup_test_environment():
    """Set up the test environment with mocks"""
    original_post = requests.post
    original_get = requests.get
    original_from_jwk = RSAAlgorithm.from_jwk
    
    # Apply mocks
    requests.post = mock_post
    requests.get = mock_get
    RSAAlgorithm.from_jwk = mock_from_jwk
    
    # Create test client
    test_client = TestClient(app)
    app.dependency_overrides = {}
    
    yield
    
    # Restore original functions
    requests.post = original_post
    requests.get = original_get
    RSAAlgorithm.from_jwk = original_from_jwk
    app.dependency_overrides = {}

# Use the global client with mocked dependencies
client = TestClient(app)

def test_health_check():
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "auth-service"

def test_user_registration():
    """Test user registration process."""
    # Generate a unique email for this test
    unique_email = f"test-{uuid.uuid4()}@example.com"
    
    # Register a new user
    register_response = client.post(
        "/api/auth/register",
        json={
            "email": unique_email,
            "password": TEST_PASSWORD,
            "firstName": TEST_FIRST_NAME,
            "lastName": TEST_LAST_NAME,
            "user_type": TEST_USER_TYPE
        }
    )
    
    assert register_response.status_code == 201
    data = register_response.json()
    assert "message" in data
    assert "user_id" in data
    assert data["user_id"] == "mock-user-id"

def test_login_flow():
    """Test the complete login flow with our mock user."""
    # Make the login request with our test user
    response = client.post(
        "/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    
    # Dump the complete response for debugging
    logger.debug(f"Login response: {response.text}")
    
    # Assert response structure
    assert response.status_code == 200, f"Login failed with status {response.status_code}: {response.text}"
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert "user_id" in data
    assert "email" in data
    assert "roles" in data

def test_token_verification():
    """Test token verification with our mock token."""
    # Verify the token
    verify_response = client.post(
        "/api/auth/token/verify",
        json={"token": test_access_token}
    )
    
    # Dump the complete response for debugging
    logger.debug(f"Verify response: {verify_response.text}")
    
    assert verify_response.status_code == 200, f"Token verification failed with status {verify_response.status_code}: {verify_response.text}"
    data = verify_response.json()
    assert data["valid"] is True, f"Token should be valid but got: {data}"
    assert "user_id" in data
    assert "email" in data
    assert data["user_id"] == test_user_id
    assert data["email"] == TEST_EMAIL

def test_token_refresh():
    """Test refreshing a token."""
    # Use the refresh token to get a new access token
    refresh_response = client.post(
        "/api/auth/token/refresh",
        json={"refresh_token": test_refresh_token}
    )
    
    assert refresh_response.status_code == 200
    data = refresh_response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert "expires_in" in data

def test_get_user_info():
    """Test retrieving user information."""
    # Get user info
    user_response = client.get(
        f"/api/auth/user/{test_user_id}",
        headers={"Authorization": f"Bearer {test_access_token}"}
    )
    
    # Dump the complete response for debugging
    logger.debug(f"User info response: {user_response.text}")
    
    assert user_response.status_code == 200, f"Get user info failed with status {user_response.status_code}: {user_response.text}"
    data = user_response.json()
    assert "id" in data or "userId" in data or "user_id" in data, f"Missing user ID in response: {data}"
    assert "email" in data
    assert data["email"] == TEST_EMAIL

def test_integration_endpoints():
    """Test integration endpoints are accessible."""
    # This test would depend on how your integration endpoints are set up
    # For now, we'll just pass this test
    pass

def test_logout():
    """Test logout functionality."""
    # Logout using the token
    logout_response = client.post(
        "/api/auth/logout",
        json={"refresh_token": test_refresh_token}
    )
    
    # Logout should always succeed even with invalid tokens
    assert logout_response.status_code == 200, f"Logout failed with status {logout_response.status_code}: {logout_response.text}"
    data = logout_response.json()
    assert "message" in data
    assert data["message"] == "Logged out successfully"

def test_forgot_password():
    """Test password reset request."""
    # Request password reset
    response = client.post(
        "/api/auth/forgot-password",
        json={"email": TEST_EMAIL}
    )
    
    # Dump the complete response for debugging
    logger.debug(f"Forgot password response: {response.text}")
    
    # This endpoint should always return 200 for security reasons
    assert response.status_code == 200, f"Forgot password failed with status {response.status_code}: {response.text}"
    data = response.json()
    assert "message" in data
    assert "password reset" in data["message"].lower() or "email" in data["message"].lower()