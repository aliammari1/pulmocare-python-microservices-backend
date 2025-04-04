from typing import Dict, List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Path, status
from middleware.keycloak_auth import get_current_user
from pydantic import BaseModel
from services.keycloak_service import KeycloakService

router = APIRouter(prefix="/api/auth/integration", tags=["Integration"])


class ServiceIdentityModel(BaseModel):
    service_name: str
    service_token: str


class ServiceVerificationResponse(BaseModel):
    valid: bool
    service_name: Optional[str] = None
    roles: Optional[List[str]] = None
    error: Optional[str] = None


@router.post("/verify-service", response_model=ServiceVerificationResponse)
async def verify_service_identity(request: ServiceIdentityModel):
    """Verify a service identity token for service-to-service communication"""
    try:
        # This endpoint would verify service identity tokens
        # For now, we'll just return a placeholder
        # In a real implementation, you would verify the token against Keycloak or another service
        return ServiceVerificationResponse(
            valid=True, service_name=request.service_name, roles=["service"]
        )
    except Exception as e:
        return ServiceVerificationResponse(valid=False, error=str(e))


@router.get("/user-roles/{user_id}", response_model=Dict[str, List[str]])
async def get_user_roles(
    user_id: str = Path(...), current_user: dict = Depends(get_current_user)
):
    """Get roles for a specific user (requires admin privileges)"""
    # Check if current user has admin permissions
    if "admin" not in current_user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )

    # In a real implementation, this would fetch roles from Keycloak
    # For now, return a placeholder
    return {"roles": ["user"]}


router = APIRouter(prefix="/api/auth/diagnostics", tags=["diagnostics"])

class DiagnosticsResponse(BaseModel):
    results: Dict[str, Any]
    
@router.get("/keycloak", response_model=DiagnosticsResponse)
async def test_keycloak_connection(user_info: dict = Depends(get_current_user)):
    """
    Test Keycloak connection and configuration
    This endpoint requires authentication to prevent exposing sensitive information
    """
    # Verify the user has admin privileges
    if "admin" not in user_info.get("roles", []):
        raise HTTPException(status_code=403, detail="Only administrators can access this endpoint")
        
    keycloak_service = KeycloakService()
    results = keycloak_service.test_connection()
    
    return {"results": results}
