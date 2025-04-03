import os
from typing import Dict

import jwt
import requests
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# Load environment variables
env = os.getenv("ENV", "development")
dotenv_file = f".env.{env}"
if not os.path.exists(dotenv_file):
    dotenv_file = ".env"
load_dotenv(dotenv_path=dotenv_file)

# Keycloak configuration
KEYCLOAK_BASE_URL = os.getenv("KEYCLOAK_BASE_URL", "http://localhost:8080")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "medapp")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "medapp-client")
KEYCLOAK_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "")

# Load JWT secret from environment or use default
JWT_SECRET_KEY = os.getenv("JWT_SECRET", "replace-with-strong-secret")

# Create HTTP bearer token scheme
security = HTTPBearer()


def keycloak_auth(token: str) -> Dict:
    """
    Validate token with Keycloak and return user info
    """
    introspect_url = f"{KEYCLOAK_BASE_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token/introspect"

    payload = {
        "token": token,
        "client_id": KEYCLOAK_CLIENT_ID,
        "client_secret": KEYCLOAK_CLIENT_SECRET,
    }

    try:
        response = requests.post(introspect_url, data=payload)
        response.raise_for_status()
        token_data = response.json()

        if not token_data.get("active", False):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is invalid or expired",
            )

        # Get user details
        user_info_url = f"{KEYCLOAK_BASE_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/userinfo"
        user_info_response = requests.get(
            user_info_url, headers={"Authorization": f"Bearer {token}"}
        )
        user_info_response.raise_for_status()
        user_info = user_info_response.json()

        return {
            "user_id": user_info.get("sub"),
            "email": user_info.get("email"),
            "name": user_info.get("name"),
            "roles": token_data.get("realm_access", {}).get("roles", []),
        }

    except requests.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Failed to validate token: {str(e)}",
        )


def verify_jwt(token: str) -> Dict:
    """
    Verify JWT token when Keycloak is not available
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
        return {"user_id": payload.get("user_id")}
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token or expired token",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict:
    """
    Get the current user from the token in the request
    """
    token = credentials.credentials

    # Try Keycloak first, fallback to JWT
    try:
        return keycloak_auth(token)
    except HTTPException:
        # Fallback to local JWT verification
        return verify_jwt(token)


async def get_current_radiologist(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict:
    """
    Get the current radiologist from the token, checking for radiologist role
    """
    user_info = await get_current_user(credentials)

    # Check if roles are available (Keycloak was used)
    if "roles" in user_info and "radiologist" not in user_info["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have radiologist role",
        )

    return user_info


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict:
    """
    Get the current admin from the token, checking for admin role
    """
    user_info = await get_current_user(credentials)

    # Check if roles are available (Keycloak was used)
    if "roles" in user_info and "admin" not in user_info["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have admin role",
        )

    return user_info
