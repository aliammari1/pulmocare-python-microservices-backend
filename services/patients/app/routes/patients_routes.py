from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import Config
from models.patient_model import ErrorResponse, MessageResponse, Patient, PatientUpdate
from services.logger_service import logger_service
from services.rabbitmq_client import RabbitMQClient

router = APIRouter(prefix="/api/patients", tags=["Patients"])

# Initialize RabbitMQ client
rabbitmq_client = RabbitMQClient(Config)

# Security and configuration setup
security = HTTPBearer()


async def get_patient_by_id(patient_id: str, token: str) -> dict:
    """
    Get patient information by ID from auth service

    Args:
        patient_id: The patient ID to look up
        token: The access token from the request

    Returns:
        Dict: The patient information

    Raises:
        HTTPException: If the patient is not found or there's a service error
    """
    try:
        # Call auth service directly to get user info
        auth_url = f"{Config.AUTH_SERVICE_URL}/api/auth/users/{patient_id}"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(auth_url, headers=headers)

            if response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Patient not found",
                )

            if response.status_code != 200:
                logger_service.error(f"Failed to get user info: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to retrieve user information",
                )

            # Get user info from response
            return response.json()

    except httpx.RequestError as e:
        logger_service.error(f"Error connecting to auth service: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Unexpected error retrieving user info: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving user information",
        )


async def get_service_token():
    """Get a service token for service-to-service communication"""
    try:
        # Create a service-to-service authentication request
        auth_url = f"{Config.AUTH_SERVICE_URL}/api/auth/token"

        # Create credentials payload
        payload = {
            "client_id": Config.AUTH_SERVICE_CLIENT_ID,
            "client_secret": Config.AUTH_SERVICE_CLIENT_SECRET,
            "grant_type": "client_credentials",
        }

        # Request token from auth service
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(auth_url, json=payload)

            if response.status_code != 200:
                logger_service.error(f"Failed to get service token: {response.status_code} - {response.text}")
                return None

            token_data = response.json()
            return token_data.get("access_token")
    except Exception as e:
        logger_service.error(f"Failed to get service token: {e!s}")
        return None


async def get_current_patient(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Get current user information from auth service.

    Verifies the token and ensures that the user has valid roles (patient, doctor, radiologist, or admin).
    Returns the user info with the token included.

    Raises:
        HTTPException: If the token is invalid or user doesn't have valid roles
    """
    try:
        token = credentials.credentials

        # Call auth service to verify token and get user info, requesting patient
        auth_url = f"{Config.AUTH_SERVICE_URL}/api/auth/token/verify"
        payload = {"token": token}

        # Create a new client instance for each request
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(auth_url, json=payload)

            if response.status_code != 200:
                logger_service.error(f"Failed to verify token: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication token",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Get user info from response
            user_info = response.json()

            # Check if the user has a valid healthcare role
            roles = user_info.get("roles", [])
            valid_roles = ["patient", "doctor", "radiologist", "admin"]

            # Log roles for debugging purposes
            logger_service.info(f"User roles: {roles}")

            if not any(role in roles for role in valid_roles):
                logger_service.error(f"User does not have valid healthcare role. Roles: {roles}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Healthcare role required (patient, doctor, radiologist or admin)",
                )

            # Add token to user info for convenience
            user_info["token"] = token

            return user_info

    except httpx.RequestError as e:
        logger_service.error(f"Error connecting to auth service: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Unexpected error during authentication: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication error",
        )


async def get_user_info(patient_id: str, token: str) -> dict | None:
    """Get user info from auth service"""
    try:
        # Create a new client for each request
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{Config.AUTH_SERVICE_URL}/api/auth/users/{patient_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        logger_service.error(f"Error fetching user info: {e}")
        return None
    except Exception as e:
        logger_service.error(f"Unexpected error: {e}")
        return None


async def update_user_attributes(patient_id: str, attributes: dict, token: str) -> dict | None:
    """Update user attributes in auth service"""
    try:
        # Create a new client for each request
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.put(
                f"{Config.AUTH_SERVICE_URL}/api/patients/{patient_id}/attributes",
                json=attributes,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        logger_service.error(f"Error updating user attributes: {e}")
        return None
    except Exception as e:
        logger_service.error(f"Unexpected error: {e}")
        return None


# Utility function for role checks
def is_healthcare_provider(roles):
    return any(role in roles for role in ["doctor", "radiologist", "admin"])


@router.get(
    "/{patient_id}",
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_patient(patient_id: str, user_info: dict = Depends(get_current_patient)):
    """Get patient information by ID"""
    try:
        current_user_id = user_info.get("user_id")
        roles = user_info.get("roles", [])
        token = user_info.get("token")

        logger_service.info(f"Accessing patient {patient_id} by user {current_user_id} with roles {roles}")

        # Only allow if the user is the patient themselves or a healthcare provider
        if patient_id != current_user_id and not is_healthcare_provider(roles):
            logger_service.error(f"Access denied: user {current_user_id} with roles {roles} attempted to access patient {patient_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this patient information",
            )

        # Get patient data using existing function - passing the token
        patient_data = await get_patient_by_id(patient_id, token)

        if not patient_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

        return patient_data

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error retrieving patient: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {e!s}",
        )


@router.post(
    "/request-appointment",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def request_appointment(
    doctor_id: str,
    requested_time: str,
    patient_id: str | None = None,
    reason: str | None = None,
    user_info: dict = Depends(get_current_patient),
):
    """Request an appointment with a doctor

    This endpoint can be called by:
    - Patients (creating appointments for themselves)
    - Doctors (creating appointments for their patients)
    - Radiologists (creating appointments for patients)
    - Admins (creating appointments for any patient)
    """
    try:
        token = user_info.get("token")
        roles = user_info.get("roles", [])

        # If patient_id is not provided, use the current user's ID
        # This handles the case when a patient is creating their own appointment
        if patient_id is None:
            patient_id = user_info.get("user_id")

        # If the current user is not an admin or healthcare provider, they can only
        # create appointments for themselves
        healthcare_provider_roles = ["doctor", "radiologist", "admin"]
        is_healthcare_provider = any(role in roles for role in healthcare_provider_roles)

        # Log the appointment creation attempt for debugging
        logger_service.info(f"Appointment request - User {user_info.get('user_id')} with roles {roles} creating appointment for patient {patient_id} with doctor {doctor_id}")

        if not is_healthcare_provider and patient_id != user_info.get("user_id"):
            logger_service.error(f"Unauthorized appointment creation: User {user_info.get('user_id')} with roles {roles} tried to create appointment for patient {patient_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only request appointments for yourself",
            )

        # Verify patient exists in auth service
        patient_data = await get_patient_by_id(patient_id, token)
        if not patient_data:
            raise HTTPException(status_code=404, detail="Patient not found")

        # Create appointment request data
        appointment_data = {
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "requested_time": requested_time,
            "reason": reason,
            "created_at": datetime.utcnow().isoformat(),
        }

        # Log the appointment creation with role information
        requester_role = "Unknown"
        for role in ["patient", "doctor", "radiologist", "admin"]:
            if role in roles:
                requester_role = role
                break

        logger_service.info(f"Appointment request initiated by {requester_role} (user ID: {user_info.get('user_id')}) for patient {patient_id} with doctor {doctor_id}")

        # Send appointment request via RabbitMQ
        message_published = rabbitmq_client.publish_appointment_request(
            patient_id=patient_id,
            doctor_id=doctor_id,
            appointment_data=appointment_data,
        )

        if message_published:
            # Generate a unique ID for the request confirmation
            appointment_request_id = f"req_{patient_id}_{doctor_id}_{int(datetime.utcnow().timestamp())}"

            # Store the appointment request ID in user attributes for reference
            # Get current appointment_requests or initialize empty list
            token = user_info.get("token")

            current_user_data = await get_user_info(patient_id, token)
            attributes = current_user_data.get("attributes", {})

            appointment_requests = attributes.get("appointment_requests", [])
            if not isinstance(appointment_requests, list):
                appointment_requests = [appointment_requests] if appointment_requests else []

            # Add the new request
            new_request = {
                "id": appointment_request_id,
                "doctor_id": doctor_id,
                "requested_time": requested_time,
                "reason": reason,
                "status": "requested",
                "created_at": datetime.utcnow().isoformat(),
            }

            # Update attributes with new request
            appointment_requests.append(new_request)
            attributes["appointment_requests"] = appointment_requests

            # Update user attributes in auth service
            await update_user_attributes(patient_id, attributes, token)

            return MessageResponse(message=f"Appointment request sent successfully. Request ID: {appointment_request_id}")
        else:
            raise HTTPException(status_code=500, detail="Failed to send appointment request")

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error requesting appointment: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e!s}")


@router.get(
    "/medical-history",
    responses={500: {"model": ErrorResponse}},
)
async def get_medical_history(user_info: dict = Depends(get_current_patient)):
    """Get patient's medical history"""
    try:
        patient_id = user_info.get("user_id")

        # Request data from other services via RabbitMQ
        logger_service.info(f"Requesting medical history data for patient {patient_id}")

        # Get prescriptions from ordonnances service
        prescriptions = rabbitmq_client.request_patient_prescriptions(patient_id)
        logger_service.info(f"Received {len(prescriptions)} prescriptions")

        # Get medical records from medecins service
        medical_records = rabbitmq_client.request_patient_medical_records(patient_id)
        logger_service.info(f"Received {len(medical_records)} medical records")

        # Get radiology reports from radiologues service
        radiology_reports = rabbitmq_client.request_patient_radiology_reports(patient_id)
        logger_service.info(f"Received {len(radiology_reports)} radiology reports")

        # Get patient demographics from auth service
        token = user_info.get("token")
        patient_data = await get_user_info(patient_id, token)

        # Extract patient attributes
        attributes = patient_data.get("attributes", {})

        # Format allergies and medical history from user attributes
        allergies = attributes.get("allergies", [])
        if not isinstance(allergies, list):
            allergies = [allergies] if allergies else []

        medical_history_items = attributes.get("medical_history", [])
        if not isinstance(medical_history_items, list):
            medical_history_items = [medical_history_items] if medical_history_items else []

        # Combine all data
        return {
            "prescriptions": prescriptions,
            "medical_records": medical_records,
            "radiology_reports": radiology_reports,
            "allergies": allergies,
            "medical_history_items": medical_history_items,
        }

    except Exception as e:
        logger_service.error(f"Error retrieving medical history: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e!s}")


@router.get(
    "/prescriptions",
    responses={500: {"model": ErrorResponse}},
)
async def get_prescriptions(user_info: dict = Depends(get_current_patient)):
    """Get patient's prescriptions"""
    try:
        patient_id = user_info.get("user_id")

        # Get prescriptions from ordonnances service via RabbitMQ
        logger_service.info(f"Requesting prescriptions for patient {patient_id}")
        prescriptions = rabbitmq_client.request_patient_prescriptions(patient_id)
        logger_service.info(f"Received {len(prescriptions)} prescriptions")

        return {"prescriptions": prescriptions}

    except Exception as e:
        logger_service.error(f"Error retrieving prescriptions: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e!s}")


@router.put(
    "/profile",
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def update_profile(update_data: PatientUpdate, user_info: dict = Depends(get_current_patient)):
    """
    Update the current patient's profile information.

    This endpoint allows patients to update their personal information,
    including height, weight, allergies, and medical_history.
    """
    try:
        patient_id = user_info.get("user_id")
        token = user_info.get("token")

        # Get existing user data
        patient_data = await get_user_info(patient_id, token)
        if not patient_data:
            raise HTTPException(status_code=404, detail="Patient not found")

        # Extract existing attributes
        attributes = patient_data.get("attributes", {})

        # Update attributes with new data
        if update_data.name is not None:
            # Split name into first and last name for Keycloak
            name_parts = update_data.name.split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""

            # These would be updated separately in Keycloak format
            attributes["firstName"] = first_name
            attributes["lastName"] = last_name

        if update_data.phone is not None:
            attributes["phone"] = update_data.phone

        if update_data.address is not None:
            attributes["address"] = update_data.address

        if update_data.date_of_birth is not None:
            attributes["date_of_birth"] = str(update_data.date_of_birth)

        if update_data.blood_type is not None:
            attributes["blood_type"] = update_data.blood_type

        if update_data.social_security_number is not None:
            attributes["social_security_number"] = update_data.social_security_number

        if update_data.medical_history is not None:
            attributes["medical_history"] = update_data.medical_history

        if update_data.allergies is not None:
            attributes["allergies"] = update_data.allergies

        if update_data.height is not None:
            attributes["height"] = str(update_data.height)

        if update_data.weight is not None:
            attributes["weight"] = str(update_data.weight)

        if update_data.medical_files is not None:
            attributes["medical_files"] = update_data.medical_files

        # Update user attributes in auth service
        auth_url = f"{Config.AUTH_SERVICE_URL}/api/auth/users/{patient_id}/attributes"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.patch(auth_url, json=attributes, headers=headers)

            if response.status_code != 200:
                logger_service.error(f"Failed to update profile: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update profile",
                )

        # Get updated user info
        updated_patient_data = await get_user_info(patient_id, token)
        patient = Patient.from_keycloak_data(updated_patient_data)

        return {"message": "Profile updated successfully", "profile": patient.to_dict()}

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error updating patient profile: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating profile: {e!s}")
