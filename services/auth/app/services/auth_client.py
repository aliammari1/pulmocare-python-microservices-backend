import logging
import os

import requests

logger = logging.getLogger("auth_client")


class AuthServiceClient:
    """
    Client to interact with the Authentication Service.
    This provides a simple interface for other services to perform auth operations.
    """

    def __init__(self, auth_service_url=None):
        """
        Initialize the Auth Service Client.

        Args:
            auth_service_url: Base URL of the auth service
        """
        self.auth_service_url = auth_service_url or os.getenv(
            "AUTH_SERVICE_URL", "http://auth-service:8086"
        )
        logger.info(
            f"Auth Service Client initialized with URL: {self.auth_service_url}"
        )

    def login(self, email, password):
        """
        Authenticate a user with their email and password.

        Args:
            email: User's email
            password: User's password

        Returns:
            Authentication result including tokens
        """
        try:
            response = requests.post(
                f"{self.auth_service_url}/api/auth/login",
                json={"email": email, "password": password},
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Login error: {str(e)}")
            if e.response:
                logger.error(
                    f"Response status: {e.response.status_code}, body: {e.response.text}"
                )
            raise

    def register(self, user_data):
        """
        Register a new user.

        Args:
            user_data: User information including email, password, etc.

        Returns:
            Registration result
        """
        try:
            response = requests.post(
                f"{self.auth_service_url}/api/auth/register", json=user_data
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Registration error: {str(e)}")
            if e.response:
                logger.error(
                    f"Response status: {e.response.status_code}, body: {e.response.text}"
                )
            raise

    def verify_token(self, token):
        """
        Verify a token with the auth service.

        Args:
            token: Token to verify

        Returns:
            Token verification result
        """
        try:
            response = requests.post(
                f"{self.auth_service_url}/api/auth/token/verify", json={"token": token}
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Token verification error: {str(e)}")
            if e.response:
                logger.error(
                    f"Response status: {e.response.status_code}, body: {e.response.text}"
                )
            raise

    def refresh_token(self, refresh_token):
        """
        Refresh an access token.

        Args:
            refresh_token: Refresh token

        Returns:
            New token information
        """
        try:
            response = requests.post(
                f"{self.auth_service_url}/api/auth/token/refresh",
                json={"refresh_token": refresh_token},
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Token refresh error: {str(e)}")
            if e.response:
                logger.error(
                    f"Response status: {e.response.status_code}, body: {e.response.text}"
                )
            raise

    def logout(self, refresh_token):
        """
        Log out a user by invalidating their refresh token.

        Args:
            refresh_token: Refresh token to invalidate

        Returns:
            Logout result
        """
        try:
            response = requests.post(
                f"{self.auth_service_url}/api/auth/logout",
                json={"refresh_token": refresh_token},
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Logout error: {str(e)}")
            if e.response:
                logger.error(
                    f"Response status: {e.response.status_code}, body: {e.response.text}"
                )
            raise

    def get_user(self, user_id, token):
        """
        Get user information.

        Args:
            user_id: User ID
            token: Access token

        Returns:
            User information
        """
        try:
            response = requests.get(
                f"{self.auth_service_url}/api/auth/user/{user_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Get user error: {str(e)}")
            if e.response:
                logger.error(
                    f"Response status: {e.response.status_code}, body: {e.response.text}"
                )
            raise

    def forgot_password(self, email):
        """
        Request a password reset.

        Args:
            email: User's email

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
        except requests.RequestException as e:
            logger.error(f"Forgot password error: {str(e)}")
            if e.response:
                logger.error(
                    f"Response status: {e.response.status_code}, body: {e.response.text}"
                )
            raise


# Create a global instance that can be imported directly
auth_client = AuthServiceClient()
