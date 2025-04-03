import logging
import os
from typing import Dict

import requests
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger("keycloak_auth")

security = HTTPBearer()


class KeycloakAuth:
    """
    Keycloak authentication integration for the patients service.
    """

    def __init__(self):
        """Initialize the Keycloak authentication client."""
        self.auth_service_url = os.getenv(
            "AUTH_SERVICE_URL", "http://auth-service:8000"
        )
        logger.info(f"Using auth service at: {self.auth_service_url}")

    async def login(self, email: str, password: str):
        """
        Authenticate a patient with Keycloak.

        Args:
            email: Patient's email
            password: Patient's password

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
            logger.error(f"Keycloak login error: {str(e)}")
            raise

    async def register(self, patient_data: Dict):
        """
        Register a new patient in Keycloak.

        Args:
            patient_data: Patient information (name, email, password, etc.)

        Returns:
            Registration response
        """
        try:
            # Convert patient data to expected format for auth service
            user_data = {
                "email": patient_data["email"],
                "username": patient_data.get("username", patient_data["email"]),
                "password": patient_data["password"],
                "firstName": patient_data.get("firstName")
                or (
                    patient_data.get("name", "").split()[0]
                    if patient_data.get("name")
                    else ""
                ),
                "lastName": patient_data.get("lastName")
                or (
                    " ".join(patient_data.get("name", "").split()[1:])
                    if patient_data.get("name")
                    and len(patient_data.get("name", "").split()) > 1
                    else ""
                ),
                "phone_number": patient_data.get("phoneNumber", ""),
                "user_type": "patient",
            }

            # Call auth service to register
            response = requests.post(
                f"{self.auth_service_url}/api/auth/register", json=user_data
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Keycloak registration error: {str(e)}")
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
            logger.error(f"Token verification error: {str(e)}")
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
            logger.error(f"Authentication error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

    async def get_current_patient(self, user_info: Dict = Depends(get_current_user)):
        """
        FastAPI dependency for checking if the user has the patient role.

        Args:
            user_info: The user information from get_current_user

        Returns:
            The validated patient information

        Raises:
            HTTPException: If the user doesn't have the patient role
        """
        roles = user_info.get("roles", [])
        if "patient-role" not in roles and "admin" not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Patient role required",
            )
        return user_info

    async def request_password_reset(self, email: str):
        """
        Request a password reset for a patient.

        Args:
            email: Patient's email

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
            logger.error(f"Password reset request error: {str(e)}")
            raise


# Create a global instance that can be imported directly
keycloak_auth = KeycloakAuth()

# Export dependencies for convenience
get_current_user = keycloak_auth.get_current_user
get_current_patient = keycloak_auth.get_current_patient
