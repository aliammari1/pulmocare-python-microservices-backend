import logging
from keycloak import KeycloakOpenID, KeycloakAdmin
from config import Config


class KeycloakService:
    def __init__(self, config=None):
        self.config = config or Config()
        logging.info(
            f"Initializing Keycloak service with URL: {self.config.KEYCLOAK_URL}"
        )

        # Initialize the client for regular operations
        self.keycloak_openid = KeycloakOpenID(
            server_url=self.config.KEYCLOAK_URL,
            client_id=self.config.KEYCLOAK_CLIENT_ID,
            realm_name=self.config.KEYCLOAK_REALM,
            client_secret_key=self.config.KEYCLOAK_CLIENT_SECRET,
        )

        # Initialize admin client for administrative operations
        self.keycloak_admin = KeycloakAdmin(
            server_url=self.config.KEYCLOAK_URL,
            username=self.config.KEYCLOAK_ADMIN_USERNAME,
            password=self.config.KEYCLOAK_ADMIN_PASSWORD,
            realm_name=self.config.KEYCLOAK_REALM,
            verify=True,
        )

        logging.info("Keycloak service initialized successfully")

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
            # Get token from Keycloak
            token = self.keycloak_openid.token(username, password)

            # Parse the token to get user info
            user_info = self.keycloak_openid.userinfo(token["access_token"])

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
            # Get the public key for verification
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
