import os
import requests
from typing import Dict, Any, Optional

from keycloak import KeycloakAdmin, KeycloakOpenID, KeycloakOpenIDConnection

from config import Config
from services.token_provider import TokenProvider


class KeycloakService:
    def __init__(
        self,
        config=None,
        keycloak_url=None,
        realm=None,
        client_id=None,
        client_secret=None,
    ):
        self.config = config or Config()
        self.keycloak_url = keycloak_url or os.getenv(
            "KEYCLOAK_URL", "http://localhost:8090"
        )

        # Strip trailing '/auth' if present as newer Keycloak versions don't use this path
        if self.keycloak_url.endswith("/auth"):
            print(
                f"Detected '/auth' suffix in Keycloak URL, removing it for compatibility"
            )
            self.keycloak_url = self.keycloak_url.removesuffix("/auth")
        # Print initialized URL after removing '/auth' suffix
        print(f"Initializing Keycloak service with URL: {self.keycloak_url}")

        self.realm = realm or os.getenv("KEYCLOAK_REALM", "pulmocare")
        self.client_id = client_id or os.getenv("KEYCLOAK_CLIENT_ID", "pulmocare-api")
        self.client_secret = client_secret or os.getenv(
            "KEYCLOAK_CLIENT_SECRET", "pulmocare-secret"
        )

        # Endpoints
        self.token_url = (
            f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/token"
        )
        self.userinfo_url = (
            f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/userinfo"
        )
        self.users_url = f"{self.keycloak_url}/admin/realms/{self.realm}/users"

        self.keycloak_openid = KeycloakOpenID(
            server_url=self.keycloak_url,
            client_id=self.client_id,
            realm_name=self.realm,
            client_secret_key=self.client_secret,
        )

        # Create a connection with service account
        print(
            f"Setting up KeycloakOpenIDConnection with client credentials for {self.client_id}"
        )
        self.keycloak_connection = KeycloakOpenIDConnection(
            server_url=self.keycloak_url,
            realm_name=self.realm,
            client_id=self.client_id,
            client_secret_key=self.client_secret,
            verify=True,
        )

        # Initialize admin client for administrative operations using service account
        self.keycloak_admin = KeycloakAdmin(connection=self.keycloak_connection)
        print("Keycloak service initialized with service account credentials")

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

                # Get token claims to extract role
                token_info = self.keycloak_openid.decode_token(token["access_token"])
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
                    print(f"Login failed: {token_response.text}")
                    raise Exception(f"Authentication failed: {token_response.text}")

                token = token_response.json()

                # Get user info
                userinfo_response = requests.get(
                    self.userinfo_url,
                    headers={"Authorization": f"Bearer {token['access_token']}"},
                )

                if userinfo_response.status_code != 200:
                    print(f"Failed to get user info: {userinfo_response.text}")
                    raise Exception("Failed to get user info")

                user_info = userinfo_response.json()

                # Decode token to get roles
                token_info = self.verify_token(token["access_token"])

            # Extract role from realm_access roles or attributes
            user_role = None

            # First try to get role from realm_access in the token
            if (
                token_info
                and "realm_access" in token_info
                and "roles" in token_info["realm_access"]
            ):
                roles = token_info["realm_access"]["roles"]
                # Look for role-specific roles (patient-role, doctor-role, etc.)
                for role in roles:
                    if role.endswith("-role") and role != "default-roles-pulmocare":
                        user_role = role  # Keep the full role name including '-role'
                        break
                    elif role == "admin":
                        user_role = "admin"
                        break

            # If no role found in token, try to get from user attributes
            if (
                not user_role
                and "attributes" in user_info
                and "role" in user_info["attributes"]
            ):
                role_attr = user_info["attributes"]["role"]
                if isinstance(role_attr, list) and role_attr:
                    user_role = role_attr[0]  # Keep the original format
                elif isinstance(role_attr, str):
                    user_role = role_attr  # Keep the original format

            # Check for a role without the suffix and add it if needed
            if user_role and user_role not in [
                "admin",
                "patient-role",
                "doctor-role",
                "radiologist-role",
            ]:
                # If it's one of our standard roles but missing the suffix, add it back
                if user_role in ["patient", "doctor", "radiologist"]:
                    user_role = f"{user_role}-role"

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
                "role": user_role,
            }
        except Exception as e:
            print(f"Login error: {str(e)}")
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
                - role (optional, defaults to "patient")

        Returns:
            str: User ID of the created user
        """
        try:
            # Determine role name based on role type
            role = user_data.get("role", "patient").lower()
            # Special case for admin role which doesn't have "-role" suffix in realm config
            role_name = role if role == "admin" else f"{role}-role"

            # Log the registration attempt
            print(f"Registration attempt for user: {user_data.get('email')}")
            print(
                f"Attempting to create user: {user_data.get('email')} with role: {role_name}"
            )

            # Verify the service account token is valid
            try:
                # Ensure we have a valid service account token
                if not self.keycloak_admin.connection.token:
                    # Try to get a service account token
                    print(
                        "Service account token missing, attempting to get a new token..."
                    )

                    # Get a fresh client credentials token
                    response = requests.post(
                        self.token_url,
                        data={
                            "client_id": self.client_id,
                            "client_secret": self.client_secret,
                            "grant_type": "client_credentials",
                        },
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )

                    if response.status_code != 200:
                        print(f"Failed to get service account token: {response.text}")
                        raise Exception(
                            f"Failed to get service account token: HTTP {response.status_code}"
                        )

                    # Update the connection token
                    self.keycloak_connection.token = response.json()

                # Test the token with a basic operation
                test_token = self.keycloak_admin.connection.token.get("access_token")
                test_response = requests.get(
                    f"{self.keycloak_url}/admin/realms/{self.realm}/roles",
                    headers={"Authorization": f"Bearer {test_token}"},
                )

                if test_response.status_code != 200:
                    print(
                        f"Service account token validation failed: {test_response.status_code} - {test_response.text}"
                    )
                    raise Exception(
                        f"Invalid service account token: HTTP {test_response.status_code}"
                    )
                else:
                    print("Service account token validated successfully")
            except Exception as e:
                print(f"Service account token validation error: {str(e)}")
                # Re-initialize the admin client with a fresh connection
                print(
                    "Re-initializing Keycloak admin client with fresh service account credentials"
                )
                self.keycloak_connection = KeycloakOpenIDConnection(
                    server_url=self.keycloak_url,
                    realm_name=self.realm,
                    client_id=self.client_id,
                    client_secret_key=self.client_secret,
                    verify=True,
                )
                self.keycloak_admin = KeycloakAdmin(connection=self.keycloak_connection)

            # Create user in Keycloak
            user_payload = {
                "email": user_data.get("email"),
                "username": user_data.get("username", user_data.get("email")),
                "firstName": user_data.get("firstName", ""),
                "lastName": user_data.get("lastName", ""),
                "enabled": True,
                "emailVerified": False,
                "attributes": {
                    "phone": user_data.get("phone", ""),
                    "address": user_data.get("address", ""),
                    "specialty": user_data.get("specialty", ""),
                    "role": role_name,
                },
            }

            print(f"Creating user with payload: {user_payload}")
            user_id = self.keycloak_admin.create_user(user_payload)
            print(f"User created with ID: {user_id}")

            # Set password
            print(f"Setting password for user {user_id}")
            self.keycloak_admin.set_user_password(
                user_id=user_id, password=user_data.get("password"), temporary=False
            )

            # Assign role to user
            try:
                print(f"Getting realm role: {role_name}")
                role_obj = self.keycloak_admin.get_realm_role(role_name)
                print(f"Assigning role {role_name} to user {user_id}")
                self.keycloak_admin.assign_realm_roles(user_id, [role_name])
                print(f"Role {role_name} assigned successfully")
            except Exception as e:
                print(f"Could not assign role {role_name}: {str(e)}")

            # Assign user to appropriate group
            try:
                # Map role to group name - capitalize first letter and add 's'
                if role == "admin":
                    group_name = "Administrators"
                else:
                    group_name = (
                        role.capitalize() + "s"
                    )  # e.g., "Doctors", "Patients", "Radiologists"

                print(f"Getting groups to assign user to {group_name}")
                # Get all groups and find the right one by name
                groups = self.keycloak_admin.get_groups()
                group_id = None
                for group in groups:
                    if group["name"] == group_name:
                        group_id = group["id"]
                        break

                if group_id:
                    print(
                        f"Adding user {user_id} to group {group_name} (ID: {group_id})"
                    )
                    self.keycloak_admin.group_user_add(user_id, group_id)
                    print(f"User {user_id} added to group {group_name}")
                else:
                    print(f"Warning: Group {group_name} not found")
            except Exception as e:
                print(f"Could not assign user to group {group_name}: {str(e)}")

            return user_id
        except Exception as e:
            error_msg = f"User registration error: {str(e)}"
            print(error_msg)

            # Check if this is a permission issue
            if "403" in str(e) or "Forbidden" in str(e):
                print("Permission denied. Checking Keycloak client permissions...")
                print("Permission denied. Make sure:")
                print(
                    "1. The client has 'Service Account Roles' properly configured in Keycloak"
                )
                print(
                    "2. The service account has the 'manage-users' role in realm-management"
                )
                print("3. Client service account has been granted necessary roles")

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
            config_well_known = self.keycloak_openid.well_known()
            token_info = self.keycloak_openid.decode_token(token, False)
            print(f"Decoded token info: {token_info}")
            return token_info
        except Exception as e:
            print(f"Token verification error: {str(e)}")
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
            print(f"Token refresh error: {str(e)}")
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
            print(f"Logout error: {str(e)}")
            raise

    def get_user_info_by_id(self, user_id):
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
            print(f"Get user info error: {str(e)}")
            raise

    def get_user_info_by_token(self, token):
        """
        Get user information from Keycloak

        Args:
            token (str): JWT access token

        Returns:
            dict: User information
        """
        try:
            user_info = self.keycloak_openid.userinfo(token)
            return user_info
        except Exception as e:
            print(f"Get user info error: {str(e)}")
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
            if user_data.get("phone"):
                attributes["phone"] = [user_data["phone"]]
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
            print(f"Update user error: {str(e)}")
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
                print(f"Password reset requested for non-existent email: {email}")
                return False

            user_id = users[0]["id"]

            # Send password reset email
            self.keycloak_admin.send_update_account(
                user_id=user_id, payload=["UPDATE_PASSWORD"]
            )

            return True
        except Exception as e:
            print(f"Password reset request error: {str(e)}")
            raise

    def get_admin_token(self) -> Optional[str]:
        """Get an admin token from Keycloak"""
        try:
            response = requests.post(
                self.token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                print(f"Failed to get admin token: {response.text}")
                return None

            return response.json().get("access_token")
        except Exception as e:
            print(f"Error getting admin token: {str(e)}")
            return None
