from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class AppointmentStatus(str, Enum):
    """Appointment status enum"""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    # Maintain backward compatibility
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    NO_SHOW = "no_show"


class ProviderType(str, Enum):
    """Provider type enum"""

    DOCTOR = "doctor"
    RADIOLOGIST = "radiologist"


class AppointmentTypeEnum(str, Enum):
    """Appointment type enum matching frontend"""

    INITIAL = "initial"
    FOLLOW_UP = "followUp"
    EMERGENCY = "emergency"
    CONSULTATION = "consultation"


class MedicalFile(BaseModel):
    """Medical file model for appointments"""

    id: str = Field(default_factory=lambda: str(uuid4()))
    filename: str
    file_type: str
    file_url: str
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    uploaded_by: str
    size: int | None = None
    description: str | None = None


class AppointmentType(BaseModel):
    """Appointment type model"""

    type_id: str = Field(default_factory=lambda: str(uuid4()))
    type_code: str
    name: str
    description: str
    default_duration_minutes: int = 30
    provider_type: ProviderType


class AppointmentBase(BaseModel):
    """Base appointment model"""

    patient_id: str
    provider_id: str
    provider_type: ProviderType
    appointment_type: str  # Use AppointmentTypeEnum values
    appointment_date: datetime
    duration_minutes: int = 30
    reason: str | None = None  # Added to match frontend
    notes: str | None = None
    virtual: bool = False
    meeting_link: str | None = None


class AppointmentCreate(AppointmentBase):
    """Create appointment model"""

    recurring_series_id: str | None = None
    medical_file_ids: list[str] | None = None  # Added to match frontend


class AppointmentUpdate(BaseModel):
    """Update appointment model with all fields optional"""

    provider_id: str | None = None
    appointment_date: datetime | None = None
    duration_minutes: int | None = None
    reason: str | None = None  # Added to match frontend
    notes: str | None = None
    status: AppointmentStatus | None = None
    virtual: bool | None = None
    meeting_link: str | None = None
    medical_file_ids: list[str] | None = None  # Added to match frontend


class Appointment(AppointmentBase):
    """Full appointment model with additional fields"""

    appointment_id: str = Field(default_factory=lambda: str(uuid4()))
    status: AppointmentStatus = AppointmentStatus.PENDING  # Changed default to PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    medical_files: list[MedicalFile] = []


class ProviderAvailability(BaseModel):
    """Provider availability model"""

    provider_id: str
    provider_type: ProviderType
    weekly_schedule: dict[str, list[dict[str, Any]]]  # Day -> list of time slots
    exceptions: list[dict[str, Any]]  # Special dates (holidays, time off)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TimeSlot(BaseModel):
    """Time slot model for appointment scheduling"""

    start_time: datetime
    end_time: datetime
    provider_id: str
    provider_type: ProviderType
    is_available: bool = True


class AppointmentNotification(BaseModel):
    """Appointment notification model"""

    notification_id: str = Field(default_factory=lambda: str(uuid4()))
    appointment_id: str
    recipient_id: str
    recipient_type: str  # patient, doctor, radiologist
    notification_type: str  # reminder, confirmation, cancellation
    message: str
    delivered: bool = False
    read: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WorkHours(BaseModel):
    """Work hours model for provider schedules"""

    start: int  # Hour of day (0-23)
    end: int  # Hour of day (0-23)
    break_start: int | None = None  # Optional break start hour
    break_end: int | None = None  # Optional break end hour


class ScheduleConfiguration(BaseModel):
    """Schedule configuration for a provider"""

    provider_id: str
    work_hours: dict[str, WorkHours]  # Day of week (0-6) -> work hours


class ProviderSchedule(BaseModel):
    """Provider schedule model"""

    provider_id: str
    provider_name: str | None = None
    provider_type: ProviderType
    work_hours: dict[str, WorkHours]  # Day of week (0-6) -> work hours
    exceptions: list[dict[str, Any]] = []  # Special dates (holidays, time off)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RecurrenceType(str, Enum):
    """Recurrence type enum for recurring appointments"""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class RecurringAppointment(BaseModel):
    """Recurring appointment configuration model"""

    series_id: str = Field(default_factory=lambda: str(uuid4()))
    patient_id: str
    provider_id: str
    provider_type: ProviderType
    appointment_type: str
    duration_minutes: int = 30
    start_date: datetime
    end_date: datetime
    recurrence_type: RecurrenceType
    occurrences: int
    days_of_week: list[int] | None = None
    day_of_month: int | None = None
    notes: str | None = None
    virtual: bool = False


class PaginatedAppointmentResponse(BaseModel):
    """Paginated response model for appointments"""

    items: list[Appointment]
    total: int
    page: int
    limit: int
    pages: int
