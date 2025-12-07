from typing import Dict

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from services.logger_service import LoggerService

from config import Config

logger = LoggerService()
security = HTTPBearer()


async def get_authenticated_user_from_auth_service(token: str) -> Dict:
    """
    Get current user information directly from auth service without role requirement

    Args:
        token: The access token from the request

    Returns:
        Dict: The user information with user_id and roles

    Raises:
        HTTPException: If the token is invalid
    """
    try:
        # Call auth service directly to verify token and get user info
        auth_url = f"{Config.AUTH_SERVICE_URL}/api/auth/token/verify"
        headers = {"Authorization": f"Bearer {token}"}
        # Include the token in the request body as required by the auth service
        body = {"token": token}

        # Create a new client for each request
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(auth_url, headers=headers, json=body)

            if response.status_code != 200:
                logger.error(
                    f"Auth service error: {response.status_code} - {response.text}"
                )
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Authentication failed",
                )

            # User info contains user_id and roles
            user_info = response.json()
            return user_info

    except httpx.RequestError as e:
        logger.error(f"Error connecting to auth service: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail="Authentication service unavailable",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during authentication: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Authentication error",
        )


async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict:
    """
    Get current user information from auth service

    Returns:
        Dict: The user information with user_id and roles

    Raises:
        HTTPException: If the token is invalid
    """
    token = credentials.credentials
    return await get_authenticated_user_from_auth_service(token)
