from typing import Dict

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from services.logger_service import logger_service

from config import Config

# Security scheme for Swagger UI
security = HTTPBearer()


async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Get the current authenticated user from the token.

    Args:
        credentials: HTTP Authorization header with Bearer token

    Returns:
        Dict: User information including user_id, roles, etc.

    Raises:
        HTTPException: If authentication fails
    """
    try:
        token = credentials.credentials

        # Create HTTP client with a reasonable timeout
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Send request to auth service for token verification
            response = await client.post(
                f"{Config.AUTH_SERVICE_URL}/api/auth/token/verify",
                json={"token": token},
            )

            # Raise exception for non-200 responses
            if response.status_code != 200:
                logger_service.error(
                    f"Auth service error: {response.status_code} - {response.text}"
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Get token verification data from response
            token_data = response.json()

            if not token_data or not token_data.get("valid"):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        # Add token to user_info for convenience
        token_data["token"] = token
        # Also add the raw Authorization header format for services that expect it
        token_data["authorization"] = f"Bearer {token}"
        logger_service.info(
            f"User authenticated with roles: {token_data.get('roles', [])}"
        )
        return token_data

    except httpx.RequestError as e:
        logger_service.error(f"Error connecting to auth service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Authentication error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication error: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_doctor(user_info: Dict = Depends(get_current_user)):
    """
    FastAPI dependency for checking if the user has the doctor role.

    Args:
        user_info: The user information from get_current_user

    Returns:
        The validated doctor information

    Raises:
        HTTPException: If the user doesn't have the doctor role
    """
    roles = user_info.get("roles", [])
    if "doctor" not in roles and "admin" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Doctor role required",
        )
    return user_info


async def get_current_patient(user_info: Dict = Depends(get_current_user)):
    """
    FastAPI dependency for checking if the user has the patient role.

    Args:
        user_info: The user information from get_current_user

    Returns:
        The validated patient information

    Raises:
        HTTPException: If the user doesn't have the patient role
    """

    roles = user_info.get("roles", [])
    if "patient" not in roles and "admin" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Patient role required",
        )
    return user_info


async def get_current_admin(user_info: Dict = Depends(get_current_user)):
    """
    FastAPI dependency for checking if the user has the admin role.

    Args:
        user_info: The user information from get_current_user

    Returns:
        The validated admin information

    Raises:
        HTTPException: If the user doesn't have the admin role
    """
    roles = user_info.get("roles", [])
    if "admin" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return user_info
