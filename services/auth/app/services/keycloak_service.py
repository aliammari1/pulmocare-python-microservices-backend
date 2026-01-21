import os

import requests
from keycloak import KeycloakAdmin, KeycloakOpenID, KeycloakOpenIDConnection

from config import Config
from models.auth import Role


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
        self.keycloak_url = keycloak_url or os.getenv("KEYCLOAK_URL", "http://localhost:8090")

        # Strip trailing '/auth' if present as newer Keycloak versions don't use this path
        if self.keycloak_url.endswith("/auth"):
            print("Detected '/auth' suffix in Keycloak URL, removing it for compatibility")
            self.keycloak_url = self.keycloak_url.removesuffix("/auth")
        # Print initialized URL after removing '/auth' suffix
        print(f"Initializing Keycloak service with URL: {self.keycloak_url}")

        self.realm = realm or os.getenv("KEYCLOAK_REALM", "pulmocare")
        self.client_id = client_id or os.getenv("KEYCLOAK_CLIENT_ID", "pulmocare-api")
        self.client_secret = client_secret or os.getenv("KEYCLOAK_CLIENT_SECRET", "pulmocare-secret")

        # Endpoints
        self.token_url = f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/token"
        self.userinfo_url = f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/userinfo"
        self.users_url = f"{self.keycloak_url}/admin/realms/{self.realm}/users"

        self.keycloak_openid = KeycloakOpenID(
            server_url=self.keycloak_url,
            client_id=self.client_id,
            realm_name=self.realm,
            client_secret_key=self.client_secret,
        )

        # Create a connection with service account
        print(f"Setting up KeycloakOpenIDConnection with client credentials for {self.client_id}")
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
            if token_info and "realm_access" in token_info and "roles" in token_info["realm_access"]:
                roles = token_info["realm_access"]["roles"]
                for role in roles:
                    if role != "default-roles-pulmocare":
                        user_role = Role(role)
                        break

            # If no role found in token, try to get from user attributes
            if not user_role and "attributes" in user_info and "role" in user_info["attributes"]:
                role_attr = user_info["attributes"]["role"]
                if isinstance(role_attr, list) and role_attr:
                    user_role = role_attr[0]  # Keep the original format
                elif isinstance(role_attr, str):
                    user_role = role_attr  # Keep the original format

            # Check for a role without the suffix and add it if needed
            if user_role and user_role not in [
                Role.ADMIN,
                Role.PATIENT,
                Role.DOCTOR,
                Role.RADIOLOGIST,
            ]:
                # If it's one of our standard roles but missing the suffix, add it back
                if user_role in ["patient", "doctor", "radiologist"]:
                    user_role = f"{user_role}"

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
            print(f"Login error: {e!s}")
            raise

    def register(self, user_data):
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
            # Special case for admin role which doesn't have suffix in realm config
            role_name = role if role == "admin" else f"{role}"

            # Log the registration attempt
            print(f"Registration attempt for user: {user_data.get('email')}")
            print(f"Attempting to create user: {user_data.get('email')} with role: {role_name}")

            # Verify the service account token is valid
            try:
                # Ensure we have a valid service account token
                if not self.keycloak_admin.connection.token:
                    # Try to get a service account token
                    print("Service account token missing, attempting to get a new token...")

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
                        raise Exception(f"Failed to get service account token: HTTP {response.status_code}")

                    # Update the connection token
                    self.keycloak_connection.token = response.json()

                # Test the token with a basic operation
                test_token = self.keycloak_admin.connection.token.get("access_token")
                test_response = requests.get(
                    f"{self.keycloak_url}/admin/realms/{self.realm}/roles",
                    headers={"Authorization": f"Bearer {test_token}"},
                )

                if test_response.status_code != 200:
                    print(f"Service account token validation failed: {test_response.status_code} - {test_response.text}")
                    raise Exception(f"Invalid service account token: HTTP {test_response.status_code}")
                else:
                    print("Service account token validated successfully")
            except Exception as e:
                print(f"Service account token validation error: {e!s}")
                # Re-initialize the admin client with a fresh connection
                print("Re-initializing Keycloak admin client with fresh service account credentials")
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
                    # Include doctor/radiologist fields
                    "bio": user_data.get("bio", ""),
                    "license_number": user_data.get("license_number", ""),
                    "hospital": user_data.get("hospital", ""),
                    "education": user_data.get("education", ""),
                    "experience": user_data.get("experience", ""),
                    # Include new radiologist fields
                    "signature": user_data.get("signature", ""),
                    "is_verified": user_data.get("is_verified", "false"),
                    "verification_details": str(user_data.get("verification_details", "")),
                    # Include new patient fields
                    "date_of_birth": user_data.get("date_of_birth", ""),
                    "blood_type": user_data.get("blood_type", ""),
                    "social_security_number": user_data.get("social_security_number", ""),
                    "medical_history": user_data.get("medical_history", []),
                    "allergies": user_data.get("allergies", []),
                    "height": user_data.get("height", ""),
                    "weight": user_data.get("weight", ""),
                    "medical_files": user_data.get("medical_files", []),
                },
            }

            print(f"Creating user with payload: {user_payload}")
            user_id = self.keycloak_admin.create_user(user_payload)
            print(f"User created with ID: {user_id}")

            # Set password
            print(f"Setting password for user {user_id}")
            self.keycloak_admin.set_user_password(user_id=user_id, password=user_data.get("password"), temporary=False)

            # Check if the role exists and create it if it doesn't
            try:
                print(f"Checking if role {role_name} exists")
                role_exists = False

                try:
                    role_obj = self.keycloak_admin.get_realm_role(role_name)
                    if role_obj:
                        print(f"Role {role_name} exists")
                        role_exists = True
                except Exception as e:
                    if "404" in str(e) or "not found" in str(e).lower():
                        print(f"Role {role_name} does not exist")
                        role_exists = False
                    else:
                        print(f"Error checking if role exists: {e!s}")
                        raise e

                # Create the role if it doesn't exist
                if not role_exists:
                    print(f"Creating role {role_name}")
                    self.keycloak_admin.create_realm_role(
                        {
                            "name": role_name,
                            "description": f"Role for {role}s",
                        }
                    )
                    print(f"Role {role_name} created successfully")
            except Exception as e:
                print(f"Error creating role {role_name}: {e!s}")
                # Continue with registration even if role creation fails

            # Assign role to user
            try:
                print(f"Assigning roleee {role_name} to user {user_id}")
                self.keycloak_admin.assign_realm_roles(user_id, role_name)
                print(f"Role {role_name} assigned successfully")
            except Exception as e:
                print(f"Could not assign role {role_name}: {e!s}")
                # Try using direct API call if the Keycloak client method fails
                try:
                    print(f"Trying alternative method to assign role {role_name}")
                    admin_token = self.get_admin_token()
                    if admin_token:
                        # First, get the role representation
                        role_info_url = f"{self.keycloak_url}/admin/realms/{self.realm}/roles/{role_name}"
                        role_info_response = requests.get(
                            role_info_url,
                            headers={"Authorization": f"Bearer {admin_token}"},
                        )

                        if role_info_response.status_code != 200:
                            print(f"Error fetching role info: {role_info_response.status_code} - {role_info_response.text}")
                            raise Exception(f"Role not found: {role_name}")

                        role_info = role_info_response.json()

                        # Now assign the role using the role representation
                        role_url = f"{self.keycloak_url}/admin/realms/{self.realm}/users/{user_id}/role-mappings/realm"
                        role_payload = [role_info]

                        print(f"Role payload: {role_payload}")
                        response = requests.post(
                            role_url,
                            json=role_payload,
                            headers={
                                "Authorization": f"Bearer {admin_token}",
                                "Content-Type": "application/json",
                            },
                        )

                        if response.status_code in [200, 201, 204]:
                            print(f"Role {role_name} assigned using direct API call")
                        else:
                            print(f"Failed to assign role using direct API: HTTP {response.status_code} - {response.text}")
                    else:
                        print("Could not get admin token for direct role assignment")
                except Exception as direct_e:
                    print(f"Direct role assignment failed: {direct_e!s}")

            # Assign user to appropriate group
            try:
                # Map role to group name - capitalize first letter and add 's'
                if role == "admin":
                    group_name = "Administrators"
                else:
                    group_name = role.capitalize() + "s"  # e.g., "Doctors", "Patients", "Radiologists"

                print(f"Getting groups to assign user to {group_name}")
                # Get all groups and find the right one by name
                groups = self.keycloak_admin.get_groups()
                group_id = None
                for group in groups:
                    if group["name"] == group_name:
                        group_id = group["id"]
                        break

                if group_id:
                    print(f"Adding user {user_id} to group {group_name} (ID: {group_id})")
                    self.keycloak_admin.group_user_add(user_id, group_id)
                    print(f"User {user_id} added to group {group_name}")
                else:
                    print(f"Warning: Group {group_name} not found")
                    # Try to create the group if it doesn't exist
                    try:
                        print(f"Creating missing group: {group_name}")
                        group_id = self.keycloak_admin.create_group({"name": group_name})
                        if group_id:
                            print(f"Group {group_name} created with ID: {group_id}")
                            self.keycloak_admin.group_user_add(user_id, group_id)
                            print(f"User {user_id} added to newly created group {group_name}")
                    except Exception as ge:
                        print(f"Error creating group {group_name}: {ge!s}")
            except Exception as e:
                print(f"Could not assign user to group: {e!s}")

            return user_id
        except Exception as e:
            error_msg = f"User registration error: {e!s}"
            print(error_msg)

            # Check if this is a permission issue
            if "403" in str(e) or "Forbidden" in str(e):
                print("Permission denied. Checking Keycloak client permissions...")
                print("Permission denied. Make sure:")
                print("1. The client has 'Service Account Roles' properly configured in Keycloak")
                print("2. The service account has the 'manage-users' role in realm-management")
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
            print(f"Token verification error: {e!s}")
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
            print(f"Token refresh error: {e!s}")
            raise

    def logout(self, refresh_token):
        """
        Log out a user by invalidating their refresh token
        """
        try:
            # Get the admin client config for logout
            config = self.keycloak_admin.connection.get_config()
            server_url = config["server_url"]
            client_id = self.config.KEYCLOAK_CLIENT_ID
            client_secret = self.config.KEYCLOAK_CLIENT_SECRET
            realm_name = self.config.KEYCLOAK_REALM

            # Construct the logout URL
            logout_url = f"{server_url}/realms/{realm_name}/protocol/openid-connect/logout"

            # Send the logout request
            response = requests.post(
                logout_url,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                },
            )

            if response.status_code != 204:
                print(f"Keycloak logout response: {response.status_code} {response.text}")

            response.raise_for_status()
            return True
        except Exception as e:
            print(f"Error during logout: {e!s}")
            raise

    def logout_from_access_token(self, access_token):
        """
        Log out a user using their access token
        """
        try:
            # Decode the access token to get user session information
            payload = self.verify_token(access_token)
            session_id = payload.get("sid")
            user_id = payload.get("sub")

            # If no session ID or user ID, we can't proceed
            if not session_id or not user_id:
                print("No session ID or user ID in the token, can't logout")
                return False

            # Use admin API to logout specific session for user
            try:
                # Try to log out all sessions for this user
                self.keycloak_admin.logout_all_sessions(user_id)
                print(f"Successfully logged out all sessions for user {user_id}")
                return True
            except Exception as e:
                print(f"Error logging out all sessions: {e}")

                # If that fails, try to log out a specific session
                try:
                    # Need to use a direct API call since there's no method for single session logout
                    admin_url = self.keycloak_admin.connection.get_base_url()
                    admin_headers = self.keycloak_admin.connection.get_headers()
                    session_logout_url = f"{admin_url}/users/{user_id}/sessions"

                    # Get all sessions for user
                    sessions_response = requests.get(session_logout_url, headers=admin_headers)
                    if sessions_response.status_code == 200:
                        sessions = sessions_response.json()
                        for session in sessions:
                            if session.get("id") == session_id:
                                # Logout this specific session
                                logout_session_url = f"{admin_url}/sessions/{session_id}"
                                delete_response = requests.delete(logout_session_url, headers=admin_headers)
                                if delete_response.status_code in (204, 200):
                                    print(f"Successfully logged out session {session_id}")
                                    return True
                except Exception as inner_e:
                    print(f"Error in specific session logout: {inner_e}")

            return False
        except Exception as e:
            print(f"Error during logout with access token: {e!s}")
            return False

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
            print(f"Logout error: {e!s}")
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
            print(f"Get user info error: {e!s}")
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
            print(f"Get user info error: {e!s}")
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

            # Handle doctor fields
            if user_data.get("bio"):
                attributes["bio"] = [user_data["bio"]]
            if user_data.get("license_number"):
                attributes["license_number"] = [user_data["license_number"]]
            if user_data.get("hospital"):
                attributes["hospital"] = [user_data["hospital"]]
            if user_data.get("education"):
                attributes["education"] = [user_data["education"]]
            if user_data.get("experience"):
                attributes["experience"] = [user_data["experience"]]

            # Handle radiologist fields
            if "signature" in user_data:
                attributes["signature"] = [user_data["signature"]]
            if "is_verified" in user_data:
                attributes["is_verified"] = [str(user_data["is_verified"]).lower()]
            if "verification_details" in user_data:
                attributes["verification_details"] = [str(user_data["verification_details"])]

            # Handle patient specific fields
            if "date_of_birth" in user_data:
                attributes["date_of_birth"] = [user_data["date_of_birth"]]
            if "blood_type" in user_data:
                attributes["blood_type"] = [user_data["blood_type"]]
            if "social_security_number" in user_data:
                attributes["social_security_number"] = [user_data["social_security_number"]]
            if "medical_history" in user_data:
                attributes["medical_history"] = user_data["medical_history"] if isinstance(user_data["medical_history"], list) else [user_data["medical_history"]]
            if "allergies" in user_data:
                attributes["allergies"] = user_data["allergies"] if isinstance(user_data["allergies"], list) else [user_data["allergies"]]
            if "height" in user_data:
                attributes["height"] = [str(user_data["height"])]
            if "weight" in user_data:
                attributes["weight"] = [str(user_data["weight"])]
            if "medical_files" in user_data:
                attributes["medical_files"] = user_data["medical_files"] if isinstance(user_data["medical_files"], list) else [user_data["medical_files"]]

            if attributes:
                update_data["attributes"] = attributes

            # Update user
            self.keycloak_admin.update_user(user_id, update_data)

            # Update password if provided
            if user_data.get("password"):
                self.keycloak_admin.set_user_password(user_id=user_id, password=user_data["password"], temporary=False)

            return True
        except Exception as e:
            print(f"Update user error: {e!s}")
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
            self.keycloak_admin.send_update_account(user_id=user_id, payload=["UPDATE_PASSWORD"])

            return True
        except Exception as e:
            print(f"Password reset request error: {e!s}")
            raise

    def get_admin_token(self) -> str | None:
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
            print(f"Error getting admin token: {e!s}")
            return None

    def sync_user_roles_from_attributes(self, user_id=None):
        """
        Synchronize user roles based on their attributes.
        This is useful for fixing existing users that have role attributes but not the corresponding realm role.

        Args:
            user_id (str, optional): Specific user ID to sync, or None to sync all users

        Returns:
            int: Number of users that were updated
        """
        try:
            updated_users = 0

            # Get users to process
            if user_id:
                users = [self.keycloak_admin.get_user(user_id)]
            else:
                users = self.keycloak_admin.get_users({})

            print(f"Syncing roles for {len(users)} users")

            for user in users:
                try:
                    user_id = user["id"]
                    user_name = user.get("username", "unknown")
                    attributes = user.get("attributes", {})

                    if not attributes or "role" not in attributes:
                        print(f"User {user_name} has no role attribute, skipping")
                        continue

                    # Get the role from attributes
                    role_attr = attributes["role"]
                    if isinstance(role_attr, list) and role_attr:
                        role_name = role_attr[0]
                    else:
                        role_name = role_attr

                    # Ensure it ends with unless it's admin
                    if role_name != "admin":
                        role_name = f"{role_name}"

                    print(f"User {user_name} has role attribute: {role_name}")

                    # Check if the role exists
                    try:
                        role_exists = True
                        self.keycloak_admin.get_realm_role(role_name)
                    except Exception:
                        role_exists = False

                    # Create the role if it doesn't exist
                    if not role_exists:
                        print(f"Creating missing role: {role_name}")
                        self.keycloak_admin.create_realm_role(
                            {
                                "name": role_name,
                                "description": f"Role for {role_name}s",
                            }
                        )

                    # Check if the user already has this role
                    current_roles = self.keycloak_admin.get_realm_roles_of_user(user_id)
                    current_role_names = [r["name"] for r in current_roles]

                    if role_name in current_role_names:
                        print(f"User {user_name} already has role {role_name}")
                        continue

                    # Assign the role to the user
                    print(f"Assigning role {role_name} to user {user_name}")
                    try:
                        self.keycloak_admin.assign_realm_roles(user_id, [role_name])
                        updated_users += 1
                        print(f"Successfully assigned role {role_name} to user {user_name}")
                    except Exception as e:
                        print(f"Error assigning role {role_name} to user {user_name}: {e!s}")
                        # Try alternative method
                        try:
                            admin_token = self.get_admin_token()
                            if admin_token:
                                role_url = f"{self.keycloak_url}/admin/realms/{self.realm}/users/{user_id}/role-mappings/realm"
                                role_payload = [
                                    {
                                        "name": role_name,
                                        "clientRole": False,
                                        "composite": False,
                                        "containerId": self.realm,
                                    }
                                ]
                                response = requests.post(
                                    role_url,
                                    json=role_payload,
                                    headers={
                                        "Authorization": f"Bearer {admin_token}",
                                        "Content-Type": "application/json",
                                    },
                                )
                                if response.status_code in [200, 201, 204]:
                                    print(f"Role {role_name} assigned to {user_name} using direct API call")
                                    updated_users += 1
                                else:
                                    print(f"Failed to assign role using direct API: HTTP {response.status_code} - {response.text}")
                            else:
                                print("Could not get admin token for direct role assignment")
                        except Exception as direct_e:
                            print(f"Direct role assignment failed: {direct_e!s}")
                except Exception as user_e:
                    print(f"Error processing user {user.get('username', 'unknown')}: {user_e!s}")
                    continue

            return updated_users
        except Exception as e:
            print(f"Error syncing user roles: {e!s}")
            return 0
