import functools
import logging
import os
import requests
from flask import request, jsonify
import jwt
from jwt.algorithms import RSAAlgorithm
import json

logger = logging.getLogger("auth_middleware")


class KeycloakMiddleware:
    """
    Middleware to handle Keycloak authentication for Flask applications.
    This provides token validation and role-based access control.
    """

    def __init__(
        self, keycloak_url=None, realm=None, client_id=None, client_secret=None
    ):
        """
        Initialize the Keycloak middleware.

        Args:
            keycloak_url: Base URL of the Keycloak server
            realm: Keycloak realm name
            client_id: Client ID for the application
            client_secret: Client secret for the application
        """
        self.keycloak_url = keycloak_url or os.getenv(
            "KEYCLOAK_URL", "http://keycloak:8080"
        )
        self.realm = realm or os.getenv("KEYCLOAK_REALM", "medapp")
        self.client_id = client_id or os.getenv("KEYCLOAK_CLIENT_ID", "medapp-api")
        self.client_secret = client_secret or os.getenv(
            "KEYCLOAK_CLIENT_SECRET", "your-client-secret"
        )

        # Cache for public key to avoid repeated requests
        self._public_key = None
        self._jwks = None

        # Well-known endpoints
        self.well_known_url = (
            f"{self.keycloak_url}/realms/{self.realm}/.well-known/openid-configuration"
        )
        self.token_introspection_url = f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/token/introspect"

        logger.info(f"Keycloak middleware initialized for realm {self.realm}")

    def get_public_key(self, kid=None):
        """
        Get the public key for token verification.

        Args:
            kid: Key ID from the token header

        Returns:
            Public key in PEM format
        """
        if not self._jwks:
            try:
                # Get the JWKS URL from the well-known endpoint
                response = requests.get(self.well_known_url)
                response.raise_for_status()
                well_known = response.json()
                jwks_uri = well_known.get("jwks_uri")

                # Get the JWKS
                response = requests.get(jwks_uri)
                response.raise_for_status()
                self._jwks = response.json()
            except Exception as e:
                logger.error(f"Error fetching JWKS: {str(e)}")
                raise

        # Find the key with matching kid
        if kid:
            for key in self._jwks.get("keys", []):
                if key.get("kid") == kid:
                    return RSAAlgorithm.from_jwk(json.dumps(key))

        # If no kid specified or not found, return the first key
        if self._jwks.get("keys"):
            return RSAAlgorithm.from_jwk(json.dumps(self._jwks["keys"][0]))

        raise Exception("No public key found in JWKS")

    def verify_token(self, token):
        """
        Verify a JWT token using the public key.

        Args:
            token: JWT token to verify

        Returns:
            Decoded token payload if valid

        Raises:
            jwt.InvalidTokenError: If token is invalid
        """
        try:
            # Get the unverified headers to extract the kid
            headers = jwt.get_unverified_header(token)
            kid = headers.get("kid")

            # Get the public key
            public_key = self.get_public_key(kid)

            # Verify the token
            options = {
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": True,
                "verify_aud": False,  # Skip audience verification
                "verify_iss": True,
                "require_exp": True,
                "require_iat": True,
                "require_nbf": False,
            }

            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                issuer=f"{self.keycloak_url}/realms/{self.realm}",
                options=options,
            )

            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            raise
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error verifying token: {str(e)}")
            raise

    def introspect_token(self, token):
        """
        Introspect a token with Keycloak server for detailed validation.

        Args:
            token: Token to introspect

        Returns:
            Token information if valid
        """
        try:
            response = requests.post(
                self.token_introspection_url,
                data={
                    "token": token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            result = response.json()

            if not result.get("active", False):
                raise jwt.InvalidTokenError("Token is not active")

            return result
        except Exception as e:
            logger.error(f"Error introspecting token: {str(e)}")
            raise

    def token_required(self, f=None, required_roles=None):
        """
        Decorator to require a valid token for accessing a route.

        Args:
            f: Function to decorate
            required_roles: List of roles required to access the route

        Returns:
            Decorated function
        """

        def decorator(f):
            @functools.wraps(f)
            def wrapper(*args, **kwargs):
                auth_header = request.headers.get("Authorization")

                if not auth_header:
                    return jsonify({"error": "Authorization header missing"}), 401

                try:
                    # Extract token from header
                    token_parts = auth_header.split()
                    if token_parts[0].lower() != "bearer" or len(token_parts) < 2:
                        return jsonify({"error": "Invalid token format"}), 401

                    token = token_parts[1]

                    # Verify token
                    payload = self.verify_token(token)

                    # Check for required roles if specified
                    if required_roles:
                        user_roles = payload.get("realm_access", {}).get("roles", [])
                        if not any(role in user_roles for role in required_roles):
                            return jsonify({"error": "Insufficient permissions"}), 403

                    # Add user info to kwargs
                    kwargs["user_id"] = payload.get("sub")
                    kwargs["user_info"] = payload

                    return f(*args, **kwargs)

                except jwt.ExpiredSignatureError:
                    return jsonify({"error": "Token expired"}), 401
                except jwt.InvalidTokenError as e:
                    return jsonify({"error": f"Invalid token: {str(e)}"}), 401
                except Exception as e:
                    logger.error(f"Authentication error: {str(e)}")
                    return jsonify({"error": "Authentication failed"}), 401

            return wrapper

        # Handle both @token_required and @token_required(required_roles=[...]) syntax
        if f is None:
            return decorator
        return decorator(f)

    def admin_required(self, f):
        """
        Decorator to require admin role for accessing a route.

        Args:
            f: Function to decorate

        Returns:
            Decorated function
        """
        return self.token_required(f, required_roles=["admin"])

    def doctor_required(self, f):
        """
        Decorator to require doctor role for accessing a route.

        Args:
            f: Function to decorate

        Returns:
            Decorated function
        """
        return self.token_required(f, required_roles=["doctor-role"])

    def patient_required(self, f):
        """
        Decorator to require patient role for accessing a route.

        Args:
            f: Function to decorate

        Returns:
            Decorated function
        """
        return self.token_required(f, required_roles=["patient-role"])

    def radiologist_required(self, f):
        """
        Decorator to require radiologist role for accessing a route.

        Args:
            f: Function to decorate

        Returns:
            Decorated function
        """
        return self.token_required(f, required_roles=["radiologist-role"])


# Create a global instance that can be imported directly
keycloak_middleware = KeycloakMiddleware()

# Export decorators for convenience
token_required = keycloak_middleware.token_required
admin_required = keycloak_middleware.admin_required
doctor_required = keycloak_middleware.doctor_required
patient_required = keycloak_middleware.patient_required
radiologist_required = keycloak_middleware.radiologist_required
