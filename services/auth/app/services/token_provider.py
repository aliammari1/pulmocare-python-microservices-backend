import os
import time
import jwt
from typing import Dict, Any, Optional

class TokenProvider:
    """
    A utility class for handling test tokens when in test mode.
    This is useful for local development and testing without a real Keycloak instance.
    """
    
    def __init__(self):
        """Initialize the token provider with configuration."""
        self.secret_key = os.getenv("TEST_JWT_SECRET_KEY", "test-secret-key")
        print("TokenProvider initialized for test mode")
        
    def create_token(self, user_data: Dict[str, Any], 
                    expires_in: int = 3600, 
                    token_type: str = "access") -> str:
        """
        Create a test JWT token.
        
        Args:
            user_data: User information to encode in the token
            expires_in: Token expiration time in seconds
            token_type: Type of token ('access' or 'refresh')
            
        Returns:
            str: JWT token
        """
        now = int(time.time())
        
        payload = {
            "iat": now,
            "exp": now + expires_in,
            "jti": f"test-{token_type}-{now}",
            # Standard JWT claims
            "sub": user_data.get("user_id", "test-user-id"),
            "preferred_username": user_data.get("username", "test-user"),
            "email": user_data.get("email", "test@example.com"),
            "name": user_data.get("name", "Test User"),
            "given_name": user_data.get("first_name", "Test"),
            "family_name": user_data.get("last_name", "User"),
            # Role information
            "realm_access": {
                "roles": user_data.get("roles", ["user"])
            }
        }
        
        return jwt.encode(payload, self.secret_key, algorithm="HS256")
        
    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify a test token.
        
        Args:
            token: JWT token to verify
            
        Returns:
            dict: Decoded token information
            
        Raises:
            jwt.InvalidTokenError: If token is invalid
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            
            # Check if token is expired
            now = int(time.time())
            if payload.get("exp", 0) < now:
                raise jwt.ExpiredSignatureError("Token has expired")
                
            return payload
        except Exception as e:
            print(f"Test token verification error: {str(e)}")
            raise
            
    def create_test_tokens(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a set of test tokens for a user.
        
        Args:
            user_data: User information
            
        Returns:
            dict: Access and refresh tokens
        """
        access_token = self.create_token(user_data, expires_in=3600, token_type="access")
        refresh_token = self.create_token(user_data, expires_in=86400, token_type="refresh")
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": 3600,
            "token_type": "bearer"
        }
