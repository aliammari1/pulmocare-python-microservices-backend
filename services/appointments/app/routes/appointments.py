from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from middleware.auth_middleware import (
    get_current_user,
    get_current_patient,
    get_current_doctor,
)
from models.appointment import (
    AppointmentCreate,
    Appointment,
    AppointmentUpdate,
    AppointmentStatus,
    PaginatedAppointmentResponse,
)
from services.appointment_service import AppointmentService
from services.logger_service import logger_service

router = APIRouter()


@router.post("/", response_model=Appointment, status_code=status.HTTP_201_CREATED)
async def create_appointment(
        appointment: AppointmentCreate, current_user: dict = Depends(get_current_user)
):
    """Create a new appointment. Only patients can create for themselves, doctors for their patients, admin for anyone."""
    roles = current_user.get("roles", [])
    user_id = current_user.get("user_id")
    if "patient" in roles:
        if appointment.patient_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Patients can only create appointments for themselves.",
            )
    elif "doctor" in roles:
        # Optionally, add logic to check if doctor is allowed to create for this patient
        pass  # Allow for now, or add more checks as needed
    elif "admin" in roles:
        pass  # Allow admin
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to create appointments.",
        )
    logger_service.info(
        f"Creating new appointment for patient {appointment.patient_id} by user {user_id}"
    )
    appointment_service = AppointmentService()
    result = await appointment_service.create_appointment(appointment, current_user)
    return result


@router.get("/{appointment_id}", response_model=Appointment)
async def get_appointment(
        appointment_id: str = Path(
            ..., description="The ID of the appointment to retrieve"
        ),
        current_user: dict = Depends(get_current_user),
):
    """Get a specific appointment by ID"""
    logger_service.info(f"Retrieving appointment {appointment_id}")
    appointment_service = AppointmentService()
    appointment = await appointment_service.get_appointment(appointment_id)

    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment with ID {appointment_id} not found",
        )
    return appointment


@router.get("/", response_model=PaginatedAppointmentResponse)
@router.get(
    "", response_model=PaginatedAppointmentResponse
)  # Also match URL without trailing slash
async def list_appointments(
        patient_id: Optional[str] = Query(None, description="Filter by patient ID"),
        provider_id: Optional[str] = Query(None, description="Filter by provider ID"),
        status: Optional[AppointmentStatus] = Query(
            None, description="Filter by appointment status"
        ),
        start_date: Optional[datetime] = Query(
            None, description="Filter by appointments after this date"
        ),
        end_date: Optional[datetime] = Query(
            None, description="Filter by appointments before this date"
        ),
        page: int = Query(1, ge=1, description="Page number"),
        limit: int = Query(10, ge=1, le=100, description="Items per page"),
        current_user: dict = Depends(get_current_user),
):
    """List appointments with optional filters"""
    logger_service.info("Listing appointments with filters")
    appointment_service = AppointmentService()

    # Default to next 30 days if no date range specified
    if not start_date:
        start_date = datetime.utcnow()
    if not end_date:
        end_date = start_date + timedelta(days=30)

    appointments = await appointment_service.list_appointments(
        patient_id=patient_id,
        provider_id=provider_id,
        status=status,
        start_date=start_date,
        end_date=end_date,
        page=page,
        limit=limit,
    )

    return appointments


@router.put("/{appointment_id}", response_model=Appointment)
async def update_appointment(
        appointment_update: AppointmentUpdate,
        appointment_id: str = Path(..., description="The ID of the appointment to update"),
        current_user: dict = Depends(get_current_user),
):
    """Update an existing appointment"""
    logger_service.info(f"Updating appointment {appointment_id}")
    appointment_service = AppointmentService()

    updated_appointment = await appointment_service.update_appointment(
        appointment_id, appointment_update
    )

    if not updated_appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment with ID {appointment_id} not found",
        )

    return updated_appointment


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_appointment(
        appointment_id: str = Path(..., description="The ID of the appointment to delete"),
        current_user: dict = Depends(get_current_user),
):
    """Cancel an appointment"""
    logger_service.info(f"Cancelling appointment {appointment_id}")
    appointment_service = AppointmentService()

    success = await appointment_service.cancel_appointment(appointment_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment with ID {appointment_id} not found",
        )

    return None
