import logging
import os
import requests
from typing import Dict, Any, Optional

from keycloak import KeycloakAdmin, KeycloakOpenID

from config import Config


class KeycloakService:
    def __init__(self, config=None):
        self.config = config or Config()
        logging.info(
            f"Initializing Keycloak service with URL: {self.config.KEYCLOAK_URL}"
        )

        self.keycloak_url = self.config.KEYCLOAK_URL
        self.realm = self.config.KEYCLOAK_REALM
        self.client_id = self.config.KEYCLOAK_CLIENT_ID
        self.client_secret = self.config.KEYCLOAK_CLIENT_SECRET
        
        # Endpoints
        self.token_url = f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/token"
        self.userinfo_url = f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/userinfo"
        self.users_url = f"{self.keycloak_url}/admin/realms/{self.realm}/users"

        # Test mode flag
        self.is_test_mode = os.getenv("AUTH_TEST_MODE", "false").lower() == "true"
        if self.is_test_mode:
            logging.info("Keycloak service running in TEST MODE")

        self.keycloak_openid = KeycloakOpenID(
            server_url=self.keycloak_url,
            client_id=self.client_id,
            realm_name=self.realm,
            client_secret_key=self.client_secret,
        )

        # Initialize admin client for administrative operations
        self.keycloak_admin = KeycloakAdmin(
            server_url=self.keycloak_url,
            username=self.config.KEYCLOAK_ADMIN_USERNAME,
            password=self.config.KEYCLOAK_ADMIN_PASSWORD,
            realm_name=self.realm,
            verify=True,
        )
        logging.info("Keycloak service initialized with native client")


    def login(self, username, password):
        """
        Authenticate a user with Keycloak

        Args:
            username (str): User's email or username
            password (str): User's password

        Returns:
            dict: Authentication tokens and user info
        """
        try:
            if self.keycloak_openid:
                # Use the Keycloak client if available
                token = self.keycloak_openid.token(username, password)
                user_info = self.keycloak_openid.userinfo(token["access_token"])
            else:
                # Fallback to direct API calls
                token_response = requests.post(
                    self.token_url,
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "grant_type": "password",
                        "username": username,
                        "password": password,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                
                if token_response.status_code != 200:
                    logging.error(f"Login failed: {token_response.text}")
                    raise Exception(f"Authentication failed: {token_response.text}")
                    
                token = token_response.json()
                
                # Get user info
                userinfo_response = requests.get(
                    self.userinfo_url,
                    headers={"Authorization": f"Bearer {token['access_token']}"},
                )
                
                if userinfo_response.status_code != 200:
                    logging.error(f"Failed to get user info: {userinfo_response.text}")
                    raise Exception("Failed to get user info")
                    
                user_info = userinfo_response.json()

            return {
                "access_token": token["access_token"],
                "refresh_token": token["refresh_token"],
                "expires_in": token["expires_in"],
                "user_id": user_info["sub"],
                "email": user_info.get("email", ""),
                "name": user_info.get("name", ""),
                "given_name": user_info.get("given_name", ""),
                "family_name": user_info.get("family_name", ""),
                "preferred_username": user_info.get("preferred_username", ""),
            }
        except Exception as e:
            logging.error(f"Login error: {str(e)}")
            raise

    def register_user(self, user_data):
        """
        Register a new user in Keycloak

        Args:
            user_data (dict): User information including at least:
                - email
                - username
                - password
                - firstName (optional)
                - lastName (optional)

        Returns:
            str: User ID of the created user
        """
        try:
            # Create user in Keycloak
            user_id = self.keycloak_admin.create_user(
                {
                    "email": user_data.get("email"),
                    "username": user_data.get("username", user_data.get("email")),
                    "firstName": user_data.get("firstName", ""),
                    "lastName": user_data.get("lastName", ""),
                    "enabled": True,
                    "emailVerified": False,
                    "attributes": {
                        "phone_number": user_data.get("phone_number", ""),
                        "address": user_data.get("address", ""),
                        "specialty": user_data.get("specialty", ""),
                        "user_type": user_data.get("user_type", "patient"),
                    },
                }
            )

            # Set password
            self.keycloak_admin.set_user_password(
                user_id=user_id, password=user_data.get("password"), temporary=False
            )

            # Optionally assign roles based on user type
            user_type = user_data.get("user_type", "patient")
            role_name = f"{user_type.lower()}-role"

            try:
                role = self.keycloak_admin.get_realm_role(role_name)
                self.keycloak_admin.assign_realm_roles(user_id, [role])
            except Exception as e:
                logging.warning(f"Could not assign role {role_name}: {str(e)}")

            return user_id
        except Exception as e:
            logging.error(f"User registration error: {str(e)}")
            raise

    def verify_token(self, token):
        """
        Verify an access token with Keycloak

        Args:
            token (str): JWT access token

        Returns:
            dict: Decoded token information
        """
        try:
            # For test mode, try our token provider first
            if self.is_test_mode:
                try:
                    return token_provider.verify_token(token)
                except Exception as e:
                    logging.debug(f"Test token verification failed: {str(e)}, trying regular verification")
                    # Continue to regular verification
            
            # Regular verification for all tokens
            JWKS = self.keycloak_openid.well_known()["jwks_uri"]
            options = {
                "verify_signature": True,
                "verify_aud": False,
                "verify_exp": True,
            }
            token_info = self.keycloak_openid.decode_token(
                token, key=JWKS, options=options
            )
            return token_info
        except Exception as e:
            logging.error(f"Token verification error: {str(e)}")
            raise

    def refresh_token(self, refresh_token):
        """
        Refresh an access token using a refresh token

        Args:
            refresh_token (str): Refresh token from previous authentication

        Returns:
            dict: New token information
        """
        try:
            token = self.keycloak_openid.refresh_token(refresh_token)
            return {
                "access_token": token["access_token"],
                "refresh_token": token["refresh_token"],
                "expires_in": token["expires_in"],
            }
        except Exception as e:
            logging.error(f"Token refresh error: {str(e)}")
            raise

    def logout(self, refresh_token):
        """
        Logout a user by invalidating their refresh token

        Args:
            refresh_token (str): Refresh token to invalidate
        """
        try:
            self.keycloak_openid.logout(refresh_token)
            return True
        except Exception as e:
            logging.error(f"Logout error: {str(e)}")
            raise

    def get_user_info(self, user_id):
        """
        Get user information from Keycloak

        Args:
            user_id (str): User ID in Keycloak

        Returns:
            dict: User information
        """
        try:
            user_info = self.keycloak_admin.get_user(user_id)
            return user_info
        except Exception as e:
            logging.error(f"Get user info error: {str(e)}")
            raise

    def update_user(self, user_id, user_data):
        """
        Update user information in Keycloak

        Args:
            user_id (str): User ID in Keycloak
            user_data (dict): User information to update

        Returns:
            bool: True if successful
        """
        try:
            # Get existing user data
            existing_user = self.keycloak_admin.get_user(user_id)

            # Update with new data
            update_data = {}
            if "email" in user_data:
                update_data["email"] = user_data["email"]
            if "firstName" in user_data:
                update_data["firstName"] = user_data["firstName"]
            if "lastName" in user_data:
                update_data["lastName"] = user_data["lastName"]

            # Handle attributes separately
            attributes = existing_user.get("attributes", {})
            if user_data.get("phone_number"):
                attributes["phone_number"] = [user_data["phone_number"]]
            if user_data.get("address"):
                attributes["address"] = [user_data["address"]]
            if user_data.get("specialty"):
                attributes["specialty"] = [user_data["specialty"]]

            if attributes:
                update_data["attributes"] = attributes

            # Update user
            self.keycloak_admin.update_user(user_id, update_data)

            # Update password if provided
            if user_data.get("password"):
                self.keycloak_admin.set_user_password(
                    user_id=user_id, password=user_data["password"], temporary=False
                )

            return True
        except Exception as e:
            logging.error(f"Update user error: {str(e)}")
            raise

    def request_password_reset(self, email):
        """
        Request a password reset for a user

        Args:
            email (str): User's email

        Returns:
            bool: True if reset email was sent
        """
        try:
            # Find user by email
            users = self.keycloak_admin.get_users({"email": email})
            if not users:
                logging.warning(
                    f"Password reset requested for non-existent email: {email}"
                )
                return False

            user_id = users[0]["id"]

            # Send password reset email
            self.keycloak_admin.send_update_account(
                user_id=user_id, payload=["UPDATE_PASSWORD"]
            )

            return True
        except Exception as e:
            logging.error(f"Password reset request error: {str(e)}")
            raise

    def get_admin_token(self) -> Optional[str]:
        """Get an admin token from Keycloak"""
        try:
            response = requests.post(
                self.token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials"
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if response.status_code != 200:
                logging.error(f"Failed to get admin token: {response.text}")
                return None
                
            return response.json().get("access_token")
        except Exception as e:
            logging.error(f"Error getting admin token: {str(e)}")
            return None
            
    def test_connection(self) -> Dict[str, Any]:
        """Test the connection to Keycloak and validate configuration"""
        results = {
            "keycloak_url": {
                "value": self.keycloak_url,
                "status": "unknown"
            },
            "realm": {
                "value": self.realm,
                "status": "unknown"
            },
            "client_id": {
                "value": self.client_id,
                "status": "unknown"
            },
            "client_credentials": {
                "status": "unknown"
            }
        }
        
        # Test basic connectivity
        try:
            response = requests.get(f"{self.keycloak_url}")
            if response.status_code < 400:
                results["keycloak_url"]["status"] = "ok"
            else:
                results["keycloak_url"]["status"] = "error"
                results["keycloak_url"]["message"] = f"HTTP {response.status_code}"
        except Exception as e:
            results["keycloak_url"]["status"] = "error"
            results["keycloak_url"]["message"] = str(e)
            
        # Test realm existence
        try:
            response = requests.get(f"{self.keycloak_url}/realms/{self.realm}")
            if response.status_code < 400:
                results["realm"]["status"] = "ok"
            else:
                results["realm"]["status"] = "error"
                results["realm"]["message"] = f"HTTP {response.status_code}"
        except Exception as e:
            results["realm"]["status"] = "error"
            results["realm"]["message"] = str(e)
            
        # Test client credentials
        try:
            response = requests.post(
                self.token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials"
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if response.status_code == 200:
                results["client_credentials"]["status"] = "ok"
                results["client_id"]["status"] = "ok"
            else:
                error_data = response.json() if response.text else {"error": "Unknown error"}
                results["client_credentials"]["status"] = "error"
                results["client_credentials"]["message"] = error_data.get("error_description", "Unknown error")
                results["client_id"]["status"] = "unknown"
        except Exception as e:
            results["client_credentials"]["status"] = "error"
            results["client_credentials"]["message"] = str(e)
            
        return results
