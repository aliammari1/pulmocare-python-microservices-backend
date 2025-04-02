import os
import logging
import requests
import json
from flask import request, jsonify
from functools import wraps

logger = logging.getLogger("keycloak_auth")


class KeycloakAuth:
    """
    Keycloak authentication integration for the radiologues service.
    """

    def __init__(self):
        """Initialize the Keycloak authentication client."""
        self.auth_service_url = os.getenv(
            "AUTH_SERVICE_URL", "http://auth-service:8086"
        )
        self.keycloak_url = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")
        self.realm = os.getenv("KEYCLOAK_REALM", "medapp")
        self.client_id = os.getenv("KEYCLOAK_CLIENT_ID", "medapp-api")
        self.client_secret = os.getenv("KEYCLOAK_CLIENT_SECRET", "your-client-secret")

        logger.info(f"Keycloak Auth initialized for radiologues service")

    def login(self, email, password):
        """
        Authenticate a radiologist with Keycloak.

        Args:
            email: Radiologist's email
            password: Radiologist's password

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

    def register(self, radiologist_data):
        """
        Register a new radiologist in Keycloak.

        Args:
            radiologist_data: Radiologist information (name, email, password, etc.)

        Returns:
            Registration response
        """
        try:
            # Convert radiologist data to expected format for auth service
            user_data = {
                "email": radiologist_data["email"],
                "username": radiologist_data.get("username", radiologist_data["email"]),
                "password": radiologist_data["password"],
                "firstName": radiologist_data.get(
                    "firstName",
                    (
                        radiologist_data.get("name", "").split()[0]
                        if radiologist_data.get("name")
                        else ""
                    ),
                ),
                "lastName": radiologist_data.get(
                    "lastName",
                    (
                        " ".join(radiologist_data.get("name", "").split()[1:])
                        if radiologist_data.get("name")
                        and len(radiologist_data.get("name", "").split()) > 1
                        else ""
                    ),
                ),
                "phone_number": radiologist_data.get("phoneNumber", ""),
                "specialty": radiologist_data.get("specialty", "Radiology"),
                "address": radiologist_data.get("address", ""),
                "user_type": "radiologist",
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

    def verify_token(self, token):
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

    def token_required(self, f):
        """
        Decorator to require a valid token for route access.

        Args:
            f: Function to decorate

        Returns:
            Decorated function
        """

        @wraps(f)
        def decorated(*args, **kwargs):
            auth_header = request.headers.get("Authorization")

            if not auth_header:
                return jsonify({"error": "Authorization header missing"}), 401

            try:
                token_parts = auth_header.split()
                if token_parts[0].lower() != "bearer" or len(token_parts) < 2:
                    return jsonify({"error": "Invalid token format"}), 401

                token = token_parts[1]

                # Verify token with auth service
                verification = self.verify_token(token)

                if not verification.get("valid", False):
                    return jsonify({"error": "Invalid token"}), 401

                # Add user info to kwargs
                kwargs["user_id"] = verification.get("user_id")
                kwargs["user_info"] = verification

                return f(*args, **kwargs)

            except Exception as e:
                logger.error(f"Authentication error: {str(e)}")
                return jsonify({"error": "Authentication failed"}), 401

        return decorated

    def radiologist_required(self, f):
        """
        Decorator to require radiologist role for route access.

        Args:
            f: Function to decorate

        Returns:
            Decorated function
        """

        @wraps(f)
        def decorated(*args, **kwargs):
            auth_header = request.headers.get("Authorization")

            if not auth_header:
                return jsonify({"error": "Authorization header missing"}), 401

            try:
                token_parts = auth_header.split()
                if token_parts[0].lower() != "bearer" or len(token_parts) < 2:
                    return jsonify({"error": "Invalid token format"}), 401

                token = token_parts[1]

                # Verify token with auth service
                verification = self.verify_token(token)

                if not verification.get("valid", False):
                    return jsonify({"error": "Invalid token"}), 401

                # Check if user has radiologist role
                roles = verification.get("roles", [])
                if "radiologist-role" not in roles and "admin" not in roles:
                    return jsonify({"error": "Radiologist role required"}), 403

                # Add user info to kwargs
                kwargs["user_id"] = verification.get("user_id")
                kwargs["user_info"] = verification

                return f(*args, **kwargs)

            except Exception as e:
                logger.error(f"Authentication error: {str(e)}")
                return jsonify({"error": "Authentication failed"}), 401

        return decorated

    def admin_required(self, f):
        """
        Decorator to require admin role for route access.

        Args:
            f: Function to decorate

        Returns:
            Decorated function
        """

        @wraps(f)
        def decorated(*args, **kwargs):
            auth_header = request.headers.get("Authorization")

            if not auth_header:
                return jsonify({"error": "Authorization header missing"}), 401

            try:
                token_parts = auth_header.split()
                if token_parts[0].lower() != "bearer" or len(token_parts) < 2:
                    return jsonify({"error": "Invalid token format"}), 401

                token = token_parts[1]

                # Verify token with auth service
                verification = self.verify_token(token)

                if not verification.get("valid", False):
                    return jsonify({"error": "Invalid token"}), 401

                # Check if user has admin role
                roles = verification.get("roles", [])
                if "admin" not in roles:
                    return jsonify({"error": "Admin role required"}), 403

                # Add user info to kwargs
                kwargs["user_id"] = verification.get("user_id")
                kwargs["user_info"] = verification

                return f(*args, **kwargs)

            except Exception as e:
                logger.error(f"Authentication error: {str(e)}")
                return jsonify({"error": "Authentication failed"}), 401

        return decorated

    def request_password_reset(self, email):
        """
        Request a password reset for a radiologist.

        Args:
            email: Radiologist's email

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

# Export decorators for convenience
token_required = keycloak_auth.token_required
radiologist_required = keycloak_auth.radiologist_required
admin_required = keycloak_auth.admin_required
