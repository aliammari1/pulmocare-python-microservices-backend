import json
import os
from typing import Any, Dict, List

import jwt
import requests
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.algorithms import RSAAlgorithm


# Security scheme for Swagger UI
security = HTTPBearer()


class KeycloakMiddleware:
    """
    Middleware to handle Keycloak authentication for FastAPI applications.
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
        
        # Strip trailing '/auth' if present as newer Keycloak versions don't use this path
        if self.keycloak_url.endswith('/auth'):
            print(f"Detected '/auth' suffix in Keycloak URL, removing it for compatibility with newer versions")
            self.keycloak_url = self.keycloak_url.removesuffix('/auth')
            
        self.realm = realm or os.getenv("KEYCLOAK_REALM", "pulmocare")
        self.client_id = client_id or os.getenv("KEYCLOAK_CLIENT_ID", "pulmocare-api")
        self.client_secret = client_secret or os.getenv(
            "KEYCLOAK_CLIENT_SECRET", "pulmocare-secret"
        )

        # Cache for public key to avoid repeated requests
        self._public_key = None
        self._jwks = None

        # Well-known endpoints
        self.well_known_url = (
            f"{self.keycloak_url}/realms/{self.realm}/.well-known/openid-configuration"
        )
        self.token_introspection_url = f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/token/introspect"

        print(f"Keycloak middleware initialized for realm {self.realm} with URL {self.keycloak_url}")

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
                print(f"Error fetching JWKS: {str(e)}")
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
            print("Token expired")
            raise
        except jwt.InvalidTokenError as e:
            print(f"Invalid token: {str(e)}")
            raise
        except Exception as e:
            print(f"Error verifying token: {str(e)}")
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
            print(f"Error introspecting token: {str(e)}")
            raise

    async def get_current_user(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(security),
        required_roles: List[str] = None,
    ) -> Dict[str, Any]:
        """
        FastAPI dependency to get the current authenticated user.

        Args:
            credentials: HTTP Bearer token credentials
            required_roles: List of roles required to access the endpoint

        Returns:
            User information from the token

        Raises:
            HTTPException: If authentication or authorization fails
        """
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header missing",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            token = credentials.credentials
            
            # Normal token verification path
            payload = self.verify_token(token)

            # Check for required roles if specified
            if required_roles:
                user_roles = payload.get("realm_access", {}).get("roles", [])
                if not any(role in user_roles for role in required_roles):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Insufficient permissions",
                    )

            # Add user ID to the payload (for convenience)
            payload["user_id"] = payload.get("sub")
            return payload

        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as e:
            print(f"Authentication error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Role-based dependencies
    async def get_admin_user(self, user=Depends(get_current_user)):
        """
        Dependency to require admin role.
        """
        return await self.get_current_user(required_roles=["admin"])

    async def get_doctor_user(self, user=Depends(get_current_user)):
        """
        Dependency to require doctor role.
        """
        return await self.get_current_user(required_roles=["doctor-role"])

    async def get_patient_user(self, user=Depends(get_current_user)):
        """
        Dependency to require patient role.
        """
        return await self.get_current_user(required_roles=["patient-role"])

    async def get_radiologist_user(self, user=Depends(get_current_user)):
        """
        Dependency to require radiologist role.
        """
        return await self.get_current_user(required_roles=["radiologist-role"])


# Create a global instance that can be imported directly
keycloak_middleware = KeycloakMiddleware()

# Export dependencies for convenience
get_current_user = keycloak_middleware.get_current_user
get_admin_user = keycloak_middleware.get_admin_user
get_doctor_user = keycloak_middleware.get_doctor_user
get_patient_user = keycloak_middleware.get_patient_user
get_radiologist_user = keycloak_middleware.get_radiologist_user
