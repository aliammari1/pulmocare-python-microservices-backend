import os
import logging
import json
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from middleware.keycloak_auth import keycloak_middleware

from config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("auth_service")

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Keycloak configuration
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "medapp")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "medapp-api")
KEYCLOAK_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "your-client-secret")

# Authentication service endpoints
TOKEN_URL = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
USERINFO_URL = (
    f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/userinfo"
)
USERS_URL = f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users"
REGISTER_URL = f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users"


# Health check endpoint
@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "service": "auth-service"}), 200


# Login endpoint
@app.route("/api/auth/login", methods=["POST"])
def login():
    try:
        data = request.get_json()

        if not data or "email" not in data or "password" not in data:
            return jsonify({"error": "Missing email or password"}), 400

        # Authenticate with Keycloak
        response = requests.post(
            TOKEN_URL,
            data={
                "client_id": KEYCLOAK_CLIENT_ID,
                "client_secret": KEYCLOAK_CLIENT_SECRET,
                "grant_type": "password",
                "username": data["email"],
                "password": data["password"],
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            logger.error(f"Keycloak login failed: {response.text}")
            return jsonify({"error": "Invalid credentials"}), 401

        token_data = response.json()

        # Get user info from access token
        userinfo_response = requests.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )

        if userinfo_response.status_code != 200:
            logger.error(f"Failed to get user info: {userinfo_response.text}")
            return jsonify({"error": "Failed to get user info"}), 500

        user_info = userinfo_response.json()

        # Return combined response
        return (
            jsonify(
                {
                    "access_token": token_data["access_token"],
                    "refresh_token": token_data["refresh_token"],
                    "expires_in": token_data["expires_in"],
                    "user_id": user_info.get("sub"),
                    "email": user_info.get("email"),
                    "name": user_info.get("name"),
                    "given_name": user_info.get("given_name"),
                    "family_name": user_info.get("family_name"),
                    "preferred_username": user_info.get("preferred_username"),
                    "roles": user_info.get("realm_access", {}).get("roles", []),
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({"error": "Authentication failed", "details": str(e)}), 500


# Token verification endpoint
@app.route("/api/auth/token/verify", methods=["POST"])
def verify_token():
    try:
        data = request.get_json()

        if not data or "token" not in data:
            return jsonify({"error": "Missing token"}), 400

        token = data["token"]

        try:
            # Verify token with Keycloak middleware
            payload = keycloak_middleware.verify_token(token)

            # Get user info
            userinfo_response = requests.get(
                USERINFO_URL, headers={"Authorization": f"Bearer {token}"}
            )

            if userinfo_response.status_code != 200:
                logger.warning(f"Failed to get user info: {userinfo_response.text}")

                # Still return basic verification if token is valid
                return (
                    jsonify(
                        {
                            "valid": True,
                            "user_id": payload.get("sub"),
                            "expires_at": payload.get("exp"),
                            "issued_at": payload.get("iat"),
                        }
                    ),
                    200,
                )

            user_info = userinfo_response.json()

            # Return combined verification
            return (
                jsonify(
                    {
                        "valid": True,
                        "user_id": payload.get("sub"),
                        "email": user_info.get("email"),
                        "name": user_info.get("name"),
                        "roles": user_info.get("realm_access", {}).get("roles", []),
                        "expires_at": payload.get("exp"),
                        "issued_at": payload.get("iat"),
                    }
                ),
                200,
            )

        except Exception as e:
            logger.warning(f"Token verification failed: {str(e)}")
            return jsonify({"valid": False, "error": str(e)}), 200

    except Exception as e:
        logger.error(f"Token verification error: {str(e)}")
        return jsonify({"error": "Verification failed", "details": str(e)}), 500


# Token refresh endpoint
@app.route("/api/auth/token/refresh", methods=["POST"])
def refresh_token():
    try:
        data = request.get_json()

        if not data or "refresh_token" not in data:
            return jsonify({"error": "Missing refresh token"}), 400

        # Refresh token with Keycloak
        response = requests.post(
            TOKEN_URL,
            data={
                "client_id": KEYCLOAK_CLIENT_ID,
                "client_secret": KEYCLOAK_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": data["refresh_token"],
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            logger.error(f"Token refresh failed: {response.text}")
            return jsonify({"error": "Invalid refresh token"}), 401

        token_data = response.json()

        # Return refreshed tokens
        return (
            jsonify(
                {
                    "access_token": token_data["access_token"],
                    "refresh_token": token_data["refresh_token"],
                    "expires_in": token_data["expires_in"],
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}")
        return jsonify({"error": "Token refresh failed", "details": str(e)}), 500


# Registration endpoint
@app.route("/api/auth/register", methods=["POST"])
def register():
    try:
        data = request.get_json()

        required_fields = ["email", "password", "firstName", "lastName"]
        missing_fields = [field for field in required_fields if field not in data]

        if missing_fields:
            return (
                jsonify(
                    {"error": f'Missing required fields: {", ".join(missing_fields)}'}
                ),
                400,
            )

        # Get admin token to create user
        admin_token_response = requests.post(
            TOKEN_URL,
            data={
                "client_id": KEYCLOAK_CLIENT_ID,
                "client_secret": KEYCLOAK_CLIENT_SECRET,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if admin_token_response.status_code != 200:
            logger.error(f"Failed to get admin token: {admin_token_response.text}")
            return jsonify({"error": "Authentication server error"}), 500

        admin_token = admin_token_response.json()["access_token"]

        # Prepare user data
        username = data.get("username", data["email"])
        user_data = {
            "username": username,
            "email": data["email"],
            "firstName": data["firstName"],
            "lastName": data["lastName"],
            "enabled": True,
            "emailVerified": True,
            "credentials": [
                {"type": "password", "value": data["password"], "temporary": False}
            ],
            "attributes": {},
        }

        # Add optional attributes
        optional_attributes = ["phone_number", "specialty", "address", "user_type"]
        for attr in optional_attributes:
            if attr in data and data[attr]:
                user_data["attributes"][attr] = [data[attr]]

        # Create user in Keycloak
        create_user_response = requests.post(
            REGISTER_URL,
            json=user_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {admin_token}",
            },
        )

        if (
            create_user_response.status_code != 201
            and create_user_response.status_code != 204
        ):
            logger.error(f"User creation failed: {create_user_response.text}")

            if create_user_response.status_code == 409:
                return jsonify({"error": "Email already registered"}), 409

            return jsonify({"error": "User registration failed"}), 500

        # Get user ID from location header or search for the user
        user_id = None
        if "Location" in create_user_response.headers:
            user_id = create_user_response.headers["Location"].split("/")[-1]
        else:
            # Search for user by username
            search_response = requests.get(
                f"{USERS_URL}?username={username}",
                headers={"Authorization": f"Bearer {admin_token}"},
            )

            if search_response.status_code == 200:
                users = search_response.json()
                if users and len(users) > 0:
                    user_id = users[0]["id"]

        if not user_id:
            logger.error("User created but ID not found")
            return jsonify({"error": "User created but failed to retrieve ID"}), 500

        # Add role based on user_type
        user_type = data.get("user_type", "").lower()
        role_name = None

        if user_type == "doctor":
            role_name = "doctor-role"
        elif user_type == "patient":
            role_name = "patient-role"
        elif user_type == "radiologist":
            role_name = "radiologist-role"
        elif user_type == "admin":
            role_name = "admin"

        if role_name:
            # Get role ID
            roles_response = requests.get(
                f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/roles",
                headers={"Authorization": f"Bearer {admin_token}"},
            )

            if roles_response.status_code == 200:
                roles = roles_response.json()
                role = next((r for r in roles if r["name"] == role_name), None)

                if role:
                    # Assign role to user
                    assign_role_response = requests.post(
                        f"{USERS_URL}/{user_id}/role-mappings/realm",
                        json=[role],
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {admin_token}",
                        },
                    )

                    if assign_role_response.status_code != 204:
                        logger.warning(
                            f"Failed to assign role: {assign_role_response.text}"
                        )
                else:
                    logger.warning(f"Role {role_name} not found")
            else:
                logger.warning(f"Failed to retrieve roles: {roles_response.text}")

        # Authenticate user to get tokens
        login_response = requests.post(
            TOKEN_URL,
            data={
                "client_id": KEYCLOAK_CLIENT_ID,
                "client_secret": KEYCLOAK_CLIENT_SECRET,
                "grant_type": "password",
                "username": data["email"],
                "password": data["password"],
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if login_response.status_code != 200:
            logger.warning(
                f"Auto-login after registration failed: {login_response.text}"
            )

            # Still return success without tokens
            return (
                jsonify(
                    {"message": "User registered successfully", "user_id": user_id}
                ),
                201,
            )

        token_data = login_response.json()

        # Return success with tokens
        return (
            jsonify(
                {
                    "message": "User registered successfully",
                    "user_id": user_id,
                    "access_token": token_data["access_token"],
                    "refresh_token": token_data["refresh_token"],
                    "expires_in": token_data["expires_in"],
                }
            ),
            201,
        )

    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return jsonify({"error": "Registration failed", "details": str(e)}), 500


# Logout endpoint
@app.route("/api/auth/logout", methods=["POST"])
def logout():
    try:
        data = request.get_json()

        if not data or "refresh_token" not in data:
            return jsonify({"error": "Missing refresh token"}), 400

        # Logout from Keycloak
        response = requests.post(
            f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/logout",
            data={
                "client_id": KEYCLOAK_CLIENT_ID,
                "client_secret": KEYCLOAK_CLIENT_SECRET,
                "refresh_token": data["refresh_token"],
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        # Return success even if Keycloak says the token was invalid
        return jsonify({"message": "Logged out successfully"}), 200

    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        return jsonify({"error": "Logout failed", "details": str(e)}), 500


# Password reset request endpoint
@app.route("/api/auth/forgot-password", methods=["POST"])
def forgot_password():
    try:
        data = request.get_json()

        if not data or "email" not in data:
            return jsonify({"error": "Missing email"}), 400

        # Get admin token
        admin_token_response = requests.post(
            TOKEN_URL,
            data={
                "client_id": KEYCLOAK_CLIENT_ID,
                "client_secret": KEYCLOAK_CLIENT_SECRET,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if admin_token_response.status_code != 200:
            logger.error(f"Failed to get admin token: {admin_token_response.text}")
            return jsonify({"error": "Authentication server error"}), 500

        admin_token = admin_token_response.json()["access_token"]

        # Find user by email
        search_response = requests.get(
            f"{USERS_URL}?email={data['email']}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        if search_response.status_code != 200 or not search_response.json():
            logger.warning(f"User not found for password reset: {data['email']}")
            return (
                jsonify(
                    {
                        "message": "If your email is registered, you will receive a password reset link"
                    }
                ),
                200,
            )

        user_id = search_response.json()[0]["id"]

        # Initiate password reset
        reset_response = requests.put(
            f"{USERS_URL}/{user_id}/execute-actions-email",
            json=["UPDATE_PASSWORD"],
            params={
                "client_id": KEYCLOAK_CLIENT_ID,
                "redirect_uri": os.getenv("FRONTEND_URL", "http://localhost:3000"),
            },
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {admin_token}",
            },
        )

        if reset_response.status_code != 204:
            logger.error(f"Password reset email failed: {reset_response.text}")
            return jsonify({"error": "Failed to send password reset email"}), 500

        return jsonify({"message": "Password reset email sent successfully"}), 200

    except Exception as e:
        logger.error(f"Password reset error: {str(e)}")
        return (
            jsonify({"error": "Password reset request failed", "details": str(e)}),
            500,
        )


# User info endpoint
@app.route("/api/auth/user/<user_id>", methods=["GET"])
@keycloak_middleware.token_required
def get_user(user_id, user_info):
    try:
        # Check if requesting own info or has admin role
        if user_id != user_info.get("sub") and "admin" not in user_info.get(
            "realm_access", {}
        ).get("roles", []):
            return jsonify({"error": "Unauthorized"}), 403

        # Get admin token
        admin_token_response = requests.post(
            TOKEN_URL,
            data={
                "client_id": KEYCLOAK_CLIENT_ID,
                "client_secret": KEYCLOAK_CLIENT_SECRET,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if admin_token_response.status_code != 200:
            logger.error(f"Failed to get admin token: {admin_token_response.text}")
            return jsonify({"error": "Authentication server error"}), 500

        admin_token = admin_token_response.json()["access_token"]

        # Get user from Keycloak
        user_response = requests.get(
            f"{USERS_URL}/{user_id}", headers={"Authorization": f"Bearer {admin_token}"}
        )

        if user_response.status_code != 200:
            logger.error(f"Failed to get user: {user_response.text}")
            return jsonify({"error": "User not found"}), 404

        user_data = user_response.json()

        # Get user roles
        roles_response = requests.get(
            f"{USERS_URL}/{user_id}/role-mappings/realm",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        roles = []
        if roles_response.status_code == 200:
            roles = [role["name"] for role in roles_response.json()]

        # Clean up sensitive data
        if "credentials" in user_data:
            del user_data["credentials"]

        if "access" in user_data:
            del user_data["access"]

        # Add roles to user data
        user_data["roles"] = roles

        return jsonify(user_data), 200

    except Exception as e:
        logger.error(f"Get user error: {str(e)}")
        return jsonify({"error": "Failed to get user info", "details": str(e)}), 500


if __name__ == "__main__":
    app.run(host=Config.HOST, port=Config.PORT, debug=True)
