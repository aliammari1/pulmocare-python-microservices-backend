import os
from typing import Dict

import requests
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer



security = HTTPBearer()


class KeycloakAuth:
    """
    Keycloak authentication integration for the radiologues service.
    """

    def __init__(self):
        """Initialize the Keycloak authentication client."""
        self.auth_service_url = os.getenv(
            "AUTH_SERVICE_URL", "http://auth-service:8086"
        )
        print(f"Using auth service at: {self.auth_service_url}")

    async def verify_token(self, token: str):
        """
        Verify a JWT token with Keycloak.

        Args:
            token: JWT token to verify

        Returns:
            Token verification result
        """
        try:
            response = requests.post(
                f"{self.auth_service_url}/api/auth/token/verify", json={"token": token}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Token verification error: {str(e)}")
            raise

    async def get_current_user(
        self, credentials: HTTPAuthorizationCredentials = Depends(security)
    ):
        """
        FastAPI dependency for extracting and validating the token from the request.

        Args:
            credentials: The HTTP Authorization header credentials

        Returns:
            The validated user information

        Raises:
            HTTPException: If the token is invalid or missing
        """
        try:
            token = credentials.credentials
            verification = await self.verify_token(token)

            if not verification.get("valid", False):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication token",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            return verification
        except Exception as e:
            print(f"Authentication error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

    async def get_current_radiologist(
        self, user_info: Dict = Depends(get_current_user)
    ):
        """
        FastAPI dependency for checking if the user has the radiologist role.

        Args:
            user_info: The user information from get_current_user

        Returns:
            The validated radiologist information

        Raises:
            HTTPException: If the user doesn't have the radiologist role
        """
        roles = user_info.get("roles", [])
        if "radiologist-role" not in roles and "admin" not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Radiologist role required",
            )
        return user_info

    async def get_current_admin(self, user_info: Dict = Depends(get_current_user)):
        """
        FastAPI dependency for checking if the user has the admin role.

        Args:
            user_info: The user information from get_current_user

        Returns:
            The validated admin information

        Raises:
            HTTPException: If the user doesn't have the admin role
        """
        roles = user_info.get("roles", [])
        if "admin" not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin role required",
            )
        return user_info


# Create a global instance that can be imported directly
keycloak_auth = KeycloakAuth()

# Export dependencies for convenience
get_current_user = keycloak_auth.get_current_user
get_current_radiologist = keycloak_auth.get_current_radiologist
get_current_admin = keycloak_auth.get_current_admin
