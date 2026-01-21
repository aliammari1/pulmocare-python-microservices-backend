from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer

from config import Config
from models.patient_model import ErrorResponse, MessageResponse
from routes.patients_routes import get_current_patient
from services.logger_service import logger_service
from services.rabbitmq_client import RabbitMQClient

router = APIRouter(prefix="/api/integration", tags=["Integration"])

# Initialize RabbitMQ client
rabbitmq_client = RabbitMQClient(Config)

# Remove the global HTTP client that causes the issue
security = HTTPBearer()


@router.get(
    "/health-systems",
    responses={500: {"model": ErrorResponse}},
)
async def list_connected_health_systems(user_info: dict = Depends(get_current_patient)):
    """List all health systems connected to this patient's account"""
    try:
        # This would typically query a database or external service
        # For now, we'll return a sample of connected health systems
        return {
            "connected_systems": [
                {
                    "id": "hs-1",
                    "name": "National Health System",
                    "connected_since": "2023-01-15T10:30:00Z",
                    "data_shared": ["demographics", "prescriptions"],
                },
                {
                    "id": "hs-2",
                    "name": "Regional Medical Center",
                    "connected_since": "2023-03-22T14:15:00Z",
                    "data_shared": ["medical_records", "radiology"],
                },
            ]
        }
    except Exception as e:
        logger_service.error(f"Error listing connected health systems: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e!s}")


@router.post(
    "/connect-health-system",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def connect_health_system(
    system_id: str,
    access_token: str,
    data_permissions: dict,
    user_info: dict = Depends(get_current_patient),
):
    """Connect a new health system to the patient's account"""
    try:
        # This would validate the access token with the external system
        # and establish the connection

        # For demonstration purposes, we'll just log the request
        patient_id = user_info.get("user_id")
        logger_service.info(f"Patient {patient_id} connecting to health system {system_id}")

        # Here we would store the connection in the database

        return MessageResponse(message=f"Successfully connected to health system {system_id}")
    except Exception as e:
        logger_service.error(f"Error connecting health system: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e!s}")


@router.post(
    "/data-request",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def request_external_data(
    system_id: str,
    data_type: str,
    date_range: dict | None = None,
    user_info: dict = Depends(get_current_patient),
):
    """Request data from an external health system"""
    try:
        patient_id = user_info.get("user_id")

        # Send data request message via RabbitMQ
        request_data = {
            "patient_id": patient_id,
            "system_id": system_id,
            "data_type": data_type,
            "date_range": date_range,
        }

        # This would publish a request that would be handled asynchronously
        request_sent = rabbitmq_client.publish_external_data_request(request_data)

        if request_sent:
            return MessageResponse(message=f"Data request for {data_type} submitted successfully. " + "You will be notified when the data is available.")
        else:
            raise HTTPException(status_code=500, detail="Failed to submit data request")
    except Exception as e:
        logger_service.error(f"Error requesting external data: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e!s}")
