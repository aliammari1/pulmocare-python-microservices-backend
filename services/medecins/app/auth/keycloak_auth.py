import os
from typing import Dict

import requests
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer



security = HTTPBearer()


class KeycloakAuth:
    """
    Keycloak authentication integration for the medecins service.
    """

    def __init__(self):
        """Initialize the Keycloak authentication client."""
        self.auth_service_url = os.getenv(
            "AUTH_SERVICE_URL", "http://auth-service:8086"
        )
        print(f"Using auth service at: {self.auth_service_url}")

    async def login(self, email: str, password: str):
        """
        Authenticate a doctor with Keycloak.

        Args:
            email: Doctor's email
            password: Doctor's password

        Returns:
            Authentication response with tokens
        """
        try:
            # Call auth service to authenticate
            response = requests.post(
                f"{self.auth_service_url}/api/auth/login",
                json={"email": email, "password": password},
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Keycloak login error: {str(e)}")
            raise

    async def register(self, doctor_data: Dict):
        """
        Register a new doctor in Keycloak.

        Args:
            doctor_data: Doctor information (name, email, password, etc.)

        Returns:
            Registration response
        """
        try:
            # Convert doctor data to expected format for auth service
            user_data = {
                "email": doctor_data["email"],
                "username": doctor_data.get("username", doctor_data["email"]),
                "password": doctor_data["password"],
                "firstName": doctor_data.get(
                    "firstName",
                    (
                        doctor_data.get("name", "").split()[0]
                        if doctor_data.get("name")
                        else ""
                    ),
                ),
                "lastName": doctor_data.get(
                    "lastName",
                    (
                        " ".join(doctor_data.get("name", "").split()[1:])
                        if doctor_data.get("name")
                        and len(doctor_data.get("name", "").split()) > 1
                        else ""
                    ),
                ),
                "phone": doctor_data.get("phone", ""),
                "specialty": doctor_data.get("specialty", ""),
                "address": doctor_data.get("address", ""),
                "role": "doctor",
            }

            # Call auth service to register
            response = requests.post(
                f"{self.auth_service_url}/api/auth/register", json=user_data
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Keycloak registration error: {str(e)}")
            raise

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

    async def get_current_doctor(self, user_info: Dict = Depends(get_current_user)):
        """
        FastAPI dependency for checking if the user has the doctor role.

        Args:
            user_info: The user information from get_current_user

        Returns:
            The validated doctor information

        Raises:
            HTTPException: If the user doesn't have the doctor role
        """
        roles = user_info.get("roles", [])
        if "doctor-role" not in roles and "admin" not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Doctor role required",
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

    async def request_password_reset(self, email: str):
        """
        Request a password reset for a doctor.

        Args:
            email: Doctor's email

        Returns:
            Password reset request result
        """
        try:
            response = requests.post(
                f"{self.auth_service_url}/api/auth/forgot-password",
                json={"email": email},
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Password reset request error: {str(e)}")
            raise


# Create a global instance that can be imported directly
keycloak_auth = KeycloakAuth()

# Export dependencies for convenience
get_current_user = keycloak_auth.get_current_user
get_current_doctor = keycloak_auth.get_current_doctor
get_current_admin = keycloak_auth.get_current_admin
