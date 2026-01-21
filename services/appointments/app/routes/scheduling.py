from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from middleware.auth_middleware import get_current_user
from models.appointment import ProviderSchedule, ProviderType, TimeSlot
from services.appointment_service import AppointmentService
from services.logger_service import logger_service

router = APIRouter()


@router.get("/available-slots", response_model=list[TimeSlot])
async def get_available_slots(
    provider_id: str | None = Query(None, description="Provider ID to check availability"),
    provider_type: ProviderType | None = Query(None, description="Type of provider (doctor or radiologist)"),
    start_date: datetime = Query(..., description="Start date for availability search"),
    end_date: datetime | None = Query(None, description="End date for availability search"),
    duration_minutes: int = Query(30, description="Duration of the appointment in minutes"),
    current_user: dict = Depends(get_current_user),
):
    """Get available appointment slots for a provider or provider type"""
    logger_service.info(f"Checking available slots for provider type {provider_type}")
    appointment_service = AppointmentService()

    # Default end date to 7 days from start if not provided
    if not end_date:
        end_date = start_date + timedelta(days=7)

    available_slots = await appointment_service.get_available_slots(
        provider_id=provider_id,
        provider_type=provider_type,
        start_date=start_date,
        end_date=end_date,
        duration_minutes=duration_minutes,
    )

    return available_slots


@router.get("/provider-schedule/{provider_id}", response_model=ProviderSchedule)
async def get_provider_schedule(
    provider_id: str = Path(..., description="The ID of the provider"),
    current_user: dict = Depends(get_current_user),
):
    """Get a provider's schedule configuration"""
    logger_service.info(f"Getting schedule for provider {provider_id}")
    appointment_service = AppointmentService()

    schedule = await appointment_service.get_provider_schedule(provider_id)

    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule for provider {provider_id} not found",
        )

    return schedule


@router.put("/provider-schedule/{provider_id}", response_model=ProviderSchedule)
async def update_provider_schedule(
    provider_schedule: ProviderSchedule,
    provider_id: str = Path(..., description="The ID of the provider"),
    current_user: dict = Depends(get_current_user),
):
    """Update a provider's schedule configuration"""
    logger_service.info(f"Updating schedule for provider {provider_id}")

    # Ensure the path parameter matches the body
    if provider_id != provider_schedule.provider_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider ID in path must match provider ID in body",
        )

    appointment_service = AppointmentService()
    updated_schedule = await appointment_service.update_provider_schedule(provider_schedule)

    return updated_schedule
