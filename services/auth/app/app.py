import logging
import os
from typing import List, Optional

import requests
from fastapi import Depends, FastAPI, HTTPException, Path, status
from fastapi.middleware.cors import CORSMiddleware
from middleware.keycloak_auth import get_user_from_token, keycloak_middleware
from pydantic import BaseModel, EmailStr

from config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("auth_service")

# Initialize FastAPI app
app = FastAPI(title="MedApp Auth Service", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update with specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Keycloak configuration
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "medapp")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "medapp-api")
KEYCLOAK_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "your-client-secret")

# Authentication service endpoints
TOKEN_URL = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
USERINFO_URL = (
    f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/userinfo"
)
USERS_URL = f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users"
REGISTER_URL = f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users"


# Pydantic models for request and response validation
class HealthCheckResponse(BaseModel):
    status: str
    service: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user_id: str
    email: str
    name: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    preferred_username: Optional[str] = None
    roles: List[str] = []


class TokenRequest(BaseModel):
    token: str


class TokenVerifyResponse(BaseModel):
    valid: bool
    user_id: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    roles: Optional[List[str]] = None
    expires_at: Optional[int] = None
    issued_at: Optional[int] = None
    error: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    firstName: str
    lastName: str
    username: Optional[str] = None
    phone_number: Optional[str] = None
    specialty: Optional[str] = None
    address: Optional[str] = None
    user_type: Optional[str] = None


class RegisterResponse(BaseModel):
    message: str
    user_id: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None


class LogoutRequest(BaseModel):
    refresh_token: str


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    error: str
    details: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


# Health check endpoint
@app.get("/health", response_model=HealthCheckResponse)
def health_check():
    return {"status": "healthy", "service": "auth-service"}


# Login endpoint
@app.post(
    "/api/auth/login",
    response_model=LoginResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def login(request: LoginRequest):
    try:
        # Authenticate with Keycloak
        response = requests.post(
            TOKEN_URL,
            data={
                "client_id": KEYCLOAK_CLIENT_ID,
                "client_secret": KEYCLOAK_CLIENT_SECRET,
                "grant_type": "password",
                "username": request.email,
                "password": request.password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            logger.error(f"Keycloak login failed: {response.text}")
            raise HTTPException(status_code=401, detail="Invalid credentials")

        token_data = response.json()

        # Get user info from access token
        userinfo_response = requests.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )

        if userinfo_response.status_code != 200:
            logger.error(f"Failed to get user info: {userinfo_response.text}")
            raise HTTPException(status_code=500, detail="Failed to get user info")

        user_info = userinfo_response.json()

        # Return combined response
        return {
            "access_token": token_data["access_token"],
            "refresh_token": token_data["refresh_token"],
            "expires_in": token_data["expires_in"],
            "user_id": user_info.get("sub"),
            "email": user_info.get("email"),
            "name": user_info.get("name"),
            "given_name": user_info.get("given_name"),
            "family_name": user_info.get("family_name"),
            "preferred_username": user_info.get("preferred_username"),
            "roles": user_info.get("realm_access", {}).get("roles", []),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")


# Token verification endpoint
@app.post("/api/auth/token/verify", response_model=TokenVerifyResponse)
async def verify_token(request: TokenRequest):
    try:
        token = request.token

        try:
            # Verify token with Keycloak middleware
            payload = keycloak_middleware.verify_token(token)

            # Get user info
            userinfo_response = requests.get(
                USERINFO_URL, headers={"Authorization": f"Bearer {token}"}
            )

            if userinfo_response.status_code != 200:
                logger.warning(f"Failed to get user info: {userinfo_response.text}")

                # Still return basic verification if token is valid
                return {
                    "valid": True,
                    "user_id": payload.get("sub"),
                    "expires_at": payload.get("exp"),
                    "issued_at": payload.get("iat"),
                }

            user_info = userinfo_response.json()

            # Return combined verification
            return {
                "valid": True,
                "user_id": payload.get("sub"),
                "email": user_info.get("email"),
                "name": user_info.get("name"),
                "roles": user_info.get("realm_access", {}).get("roles", []),
                "expires_at": payload.get("exp"),
                "issued_at": payload.get("iat"),
            }

        except Exception as e:
            logger.warning(f"Token verification failed: {str(e)}")
            return {"valid": False, "error": str(e)}

    except Exception as e:
        logger.error(f"Token verification error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")


# Token refresh endpoint
@app.post(
    "/api/auth/token/refresh",
    response_model=RefreshTokenResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def refresh_token(request: RefreshTokenRequest):
    try:
        # Refresh token with Keycloak
        response = requests.post(
            TOKEN_URL,
            data={
                "client_id": KEYCLOAK_CLIENT_ID,
                "client_secret": KEYCLOAK_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": request.refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            logger.error(f"Token refresh failed: {response.text}")
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        token_data = response.json()

        # Return refreshed tokens
        return {
            "access_token": token_data["access_token"],
            "refresh_token": token_data["refresh_token"],
            "expires_in": token_data["expires_in"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Token refresh failed: {str(e)}")


# Registration endpoint
@app.post(
    "/api/auth/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def register(request: RegisterRequest):
    try:
        # Get admin token to create user
        admin_token_response = requests.post(
            TOKEN_URL,
            data={
                "client_id": KEYCLOAK_CLIENT_ID,
                "client_secret": KEYCLOAK_CLIENT_SECRET,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if admin_token_response.status_code != 200:
            logger.error(f"Failed to get admin token: {admin_token_response.text}")
            raise HTTPException(status_code=500, detail="Authentication server error")

        admin_token = admin_token_response.json()["access_token"]

        # Prepare user data
        username = request.username or request.email
        user_data = {
            "username": username,
            "email": request.email,
            "firstName": request.firstName,
            "lastName": request.lastName,
            "enabled": True,
            "emailVerified": True,
            "credentials": [
                {"type": "password", "value": request.password, "temporary": False}
            ],
            "attributes": {},
        }

        # Add optional attributes
        optional_attributes = ["phone_number", "specialty", "address", "user_type"]
        for attr in optional_attributes:
            if hasattr(request, attr) and getattr(request, attr):
                user_data["attributes"][attr] = [getattr(request, attr)]

        # Create user in Keycloak
        create_user_response = requests.post(
            REGISTER_URL,
            json=user_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {admin_token}",
            },
        )

        if (
            create_user_response.status_code != 201
            and create_user_response.status_code != 204
        ):
            logger.error(f"User creation failed: {create_user_response.text}")

            if create_user_response.status_code == 409:
                raise HTTPException(status_code=409, detail="Email already registered")

            raise HTTPException(status_code=500, detail="User registration failed")

        # Get user ID from location header or search for the user
        user_id = None
        if "Location" in create_user_response.headers:
            user_id = create_user_response.headers["Location"].split("/")[-1]
        else:
            # Search for user by username
            search_response = requests.get(
                f"{USERS_URL}?username={username}",
                headers={"Authorization": f"Bearer {admin_token}"},
            )

            if search_response.status_code == 200:
                users = search_response.json()
                if users and len(users) > 0:
                    user_id = users[0]["id"]

        if not user_id:
            logger.error("User created but ID not found")
            raise HTTPException(
                status_code=500, detail="User created but failed to retrieve ID"
            )

        # Add role based on user_type
        user_type = request.user_type.lower() if request.user_type else ""
        role_name = None

        if user_type == "doctor":
            role_name = "doctor-role"
        elif user_type == "patient":
            role_name = "patient-role"
        elif user_type == "radiologist":
            role_name = "radiologist-role"
        elif user_type == "admin":
            role_name = "admin"

        if role_name:
            # Get role ID
            roles_response = requests.get(
                f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/roles",
                headers={"Authorization": f"Bearer {admin_token}"},
            )

            if roles_response.status_code == 200:
                roles = roles_response.json()
                role = next((r for r in roles if r["name"] == role_name), None)

                if role:
                    # Assign role to user
                    assign_role_response = requests.post(
                        f"{USERS_URL}/{user_id}/role-mappings/realm",
                        json=[role],
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {admin_token}",
                        },
                    )

                    if assign_role_response.status_code != 204:
                        logger.warning(
                            f"Failed to assign role: {assign_role_response.text}"
                        )
                else:
                    logger.warning(f"Role {role_name} not found")
            else:
                logger.warning(f"Failed to retrieve roles: {roles_response.text}")

        # Authenticate user to get tokens
        login_response = requests.post(
            TOKEN_URL,
            data={
                "client_id": KEYCLOAK_CLIENT_ID,
                "client_secret": KEYCLOAK_CLIENT_SECRET,
                "grant_type": "password",
                "username": request.email,
                "password": request.password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if login_response.status_code != 200:
            logger.warning(
                f"Auto-login after registration failed: {login_response.text}"
            )

            # Still return success without tokens
            return {"message": "User registered successfully", "user_id": user_id}

        token_data = login_response.json()

        # Return success with tokens
        return {
            "message": "User registered successfully",
            "user_id": user_id,
            "access_token": token_data["access_token"],
            "refresh_token": token_data["refresh_token"],
            "expires_in": token_data["expires_in"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


# Logout endpoint
@app.post(
    "/api/auth/logout",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def logout(request: LogoutRequest):
    try:
        # Logout from Keycloak
        response = requests.post(
            f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/logout",
            data={
                "client_id": KEYCLOAK_CLIENT_ID,
                "client_secret": KEYCLOAK_CLIENT_SECRET,
                "refresh_token": request.refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        # Return success even if Keycloak says the token was invalid
        return {"message": "Logged out successfully"}

    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Logout failed: {str(e)}")


# Password reset request endpoint
@app.post(
    "/api/auth/forgot-password",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def forgot_password(request: ForgotPasswordRequest):
    try:
        # Get admin token
        admin_token_response = requests.post(
            TOKEN_URL,
            data={
                "client_id": KEYCLOAK_CLIENT_ID,
                "client_secret": KEYCLOAK_CLIENT_SECRET,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if admin_token_response.status_code != 200:
            logger.error(f"Failed to get admin token: {admin_token_response.text}")
            raise HTTPException(status_code=500, detail="Authentication server error")

        admin_token = admin_token_response.json()["access_token"]

        # Find user by email
        search_response = requests.get(
            f"{USERS_URL}?email={request.email}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        if search_response.status_code != 200 or not search_response.json():
            logger.warning(f"User not found for password reset: {request.email}")
            return {
                "message": "If your email is registered, you will receive a password reset link"
            }

        user_id = search_response.json()[0]["id"]

        # Initiate password reset
        reset_response = requests.put(
            f"{USERS_URL}/{user_id}/execute-actions-email",
            json=["UPDATE_PASSWORD"],
            params={
                "client_id": KEYCLOAK_CLIENT_ID,
                "redirect_uri": os.getenv("FRONTEND_URL", "http://localhost:3000"),
            },
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {admin_token}",
            },
        )

        if reset_response.status_code != 204:
            logger.error(f"Password reset email failed: {reset_response.text}")
            raise HTTPException(
                status_code=500, detail="Failed to send password reset email"
            )

        return {"message": "Password reset email sent successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password reset error: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Password reset request failed: {str(e)}"
        )


# User info endpoint
@app.get(
    "/api/auth/user/{user_id}",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_user(
    user_id: str = Path(...), user_info: dict = Depends(get_user_from_token)
):
    try:
        # Check if requesting own info or has admin role
        if user_id != user_info.get("sub") and "admin" not in user_info.get(
            "realm_access", {}
        ).get("roles", []):
            raise HTTPException(status_code=403, detail="Unauthorized")

        # Get admin token
        admin_token_response = requests.post(
            TOKEN_URL,
            data={
                "client_id": KEYCLOAK_CLIENT_ID,
                "client_secret": KEYCLOAK_CLIENT_SECRET,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if admin_token_response.status_code != 200:
            logger.error(f"Failed to get admin token: {admin_token_response.text}")
            raise HTTPException(status_code=500, detail="Authentication server error")

        admin_token = admin_token_response.json()["access_token"]

        # Get user from Keycloak
        user_response = requests.get(
            f"{USERS_URL}/{user_id}", headers={"Authorization": f"Bearer {admin_token}"}
        )

        if user_response.status_code != 200:
            logger.error(f"Failed to get user: {user_response.text}")
            raise HTTPException(status_code=404, detail="User not found")

        user_data = user_response.json()

        # Get user roles
        roles_response = requests.get(
            f"{USERS_URL}/{user_id}/role-mappings/realm",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        roles = []
        if roles_response.status_code == 200:
            roles = [role["name"] for role in roles_response.json()]

        # Clean up sensitive data
        if "credentials" in user_data:
            del user_data["credentials"]

        if "access" in user_data:
            del user_data["access"]

        # Add roles to user data
        user_data["roles"] = roles

        return user_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user error: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get user info: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=Config.HOST, port=Config.PORT)
