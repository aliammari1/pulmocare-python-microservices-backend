from fastapi import APIRouter
from pydantic import BaseModel

# Integration router
router = APIRouter(prefix="/api/auth/integration", tags=["Integration"])


class ServiceIdentityModel(BaseModel):
    service_name: str
    service_token: str


class ServiceVerificationResponse(BaseModel):
    valid: bool
    service_name: str | None = None
    roles: list[str] | None = None
    error: str | None = None


@router.post("/verify-service", response_model=ServiceVerificationResponse)
async def verify_service_identity(request: ServiceIdentityModel):
    """Verify a service identity token for service-to-service communication"""
    try:
        # This endpoint would verify service identity tokens
        # For now, we'll just return a placeholder
        # In a real implementation, you would verify the token against Keycloak or another service
        return ServiceVerificationResponse(valid=True, service_name=request.service_name, roles=["service"])
    except Exception as e:
        return ServiceVerificationResponse(valid=False, error=str(e))
