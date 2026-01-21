from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from middleware.auth_middleware import (
    CurrentUser,
)
from models.appointment import (
    AppointmentStatus,
    PaginatedAppointmentResponse,
)
from services.appointment_service import AppointmentService
from services.logger_service import logger_service

router = APIRouter()


@router.get(
    "/doctor/{doctor_id}",
    response_model=PaginatedAppointmentResponse,
    dependencies=[CurrentUser],
)
async def get_doctor_appointments(
    doctor_id: Annotated[str, Query(..., description="The ID of the doctor whose appointments to retrieve")],
    page: Annotated[int, Query(1, ge=1)],
    limit: Annotated[int, Query(10, ge=1, le=100)],
    current_user: CurrentUser,
    status: Annotated[AppointmentStatus | None, Query(None)],
):
    """Get appointments for a specific doctor"""
    logger_service.info(f"Getting appointments for doctor {doctor_id}")

    # Verify the requesting user is authorized (either the doctor themselves or an admin)
    if current_user.get("user_id") != doctor_id and "admin" not in current_user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view these appointments",
        )

    appointment_service = AppointmentService()

    appointments = await appointment_service.list_appointments(
        provider_id=doctor_id,
        status=status,
        page=page,
        limit=limit,
    )

    return appointments


@router.get(
    "/patient/{patient_id}",
    response_model=PaginatedAppointmentResponse,
    dependencies=[CurrentUser],
)
async def get_patient_appointments(
    patient_id: Annotated[str, Query(..., description="The ID of the patient whose appointments to retrieve")],
    current_user: CurrentUser,
    status: Annotated[AppointmentStatus | None, Query(None)] = None,
    page: Annotated[int, Query(1, ge=1)] = 1,
    limit: Annotated[int, Query(10, ge=1, le=100)] = 10,
):
    """Get appointments for a specific patient"""
    logger_service.info(f"Getting appointments for patient {patient_id}")

    # Verify the requesting user is authorized (either the patient themselves or an admin)
    if current_user.get("user_id") != patient_id and "admin" not in current_user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view these appointments",
        )

    appointment_service = AppointmentService()

    appointments = await appointment_service.list_appointments(
        patient_id=patient_id,
        status=status,
        page=page,
        limit=limit,
    )

    return appointments


@router.get(
    "/doctor/{doctor_id}/patient/{patient_id}",
    response_model=PaginatedAppointmentResponse,
    dependencies=[CurrentUser],
)
async def get_doctor_patient_appointments(
    doctor_id: Annotated[str, Query(..., description="The ID of the doctor whose appointments to retrieve")],
    patient_id: Annotated[str, Query(..., description="The ID of the patient whose appointments to retrieve")],
    current_user: CurrentUser,
    status: Annotated[AppointmentStatus | None, Query(None)] = None,
    page: Annotated[int, Query(1, ge=1)] = 1,
    limit: Annotated[int, Query(10, ge=1, le=100)] = 10,
):
    """Get appointments between a specific doctor and patient"""
    logger_service.info(f"Getting appointments between doctor {doctor_id} and patient {patient_id}")

    # Verify the requesting user is authorized
    if current_user.get("user_id") != doctor_id and "admin" not in current_user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view these appointments",
        )

    appointment_service = AppointmentService()

    appointments = await appointment_service.list_appointments(
        provider_id=doctor_id,
        patient_id=patient_id,
        status=status,
        page=page,
        limit=limit,
    )

    return appointments
