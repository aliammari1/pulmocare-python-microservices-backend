from datetime import datetime, timedelta

import jwt
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import Config

security = HTTPBearer()


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create JWT token with given data and expiration"""
    to_encode = data.copy()

    # Set expiration time
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=1)

    to_encode.update({"exp": expire})

    # Create encoded JWT
    encoded_jwt = jwt.encode(to_encode, Config.JWT_SECRET_KEY, algorithm="HS256")
    return encoded_jwt


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> dict:
    """Validate JWT token and extract user information"""
    try:
        token = credentials.credentials
        payload = jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=["HS256"])

        # Check token expiration
        if datetime.fromtimestamp(payload.get("exp")) < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Return user info from token
        return {"user_id": payload.get("user_id")}

    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication error: {e!s}",
            headers={"WWW-Authenticate": "Bearer"},
        )
