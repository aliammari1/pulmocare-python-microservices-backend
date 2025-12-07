from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import uuid4

from pydantic import BaseModel, Field, validator


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
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    uploaded_by: str
    size: Optional[int] = None
    description: Optional[str] = None


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
    reason: Optional[str] = None  # Added to match frontend
    notes: Optional[str] = None
    virtual: bool = False
    meeting_link: Optional[str] = None


class AppointmentCreate(AppointmentBase):
    """Create appointment model"""

    recurring_series_id: Optional[str] = None
    medical_file_ids: Optional[List[str]] = None  # Added to match frontend


class AppointmentUpdate(BaseModel):
    """Update appointment model with all fields optional"""

    provider_id: Optional[str] = None
    appointment_date: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    reason: Optional[str] = None  # Added to match frontend
    notes: Optional[str] = None
    status: Optional[AppointmentStatus] = None
    virtual: Optional[bool] = None
    meeting_link: Optional[str] = None
    medical_file_ids: Optional[List[str]] = None  # Added to match frontend


class Appointment(AppointmentBase):
    """Full appointment model with additional fields"""

    appointment_id: str = Field(default_factory=lambda: str(uuid4()))
    status: AppointmentStatus = AppointmentStatus.PENDING  # Changed default to PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    medical_files: List[MedicalFile] = []  # Added to match frontend

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

    @validator("updated_at", always=True)
    def set_updated_at(cls, v, values):
        """Set updated_at to current time when updating"""
        return datetime.utcnow()

    def to_json(self) -> Dict[str, Any]:
        """Convert to format expected by frontend"""
        return {
            "id": self.appointment_id,
            "patientId": self.patient_id,
            "doctorId": self.provider_id,
            "scheduledTime": self.appointment_date.isoformat(),
            "status": self.status.value,
            "type": self.appointment_type,
            "isVirtual": self.virtual,
            "reason": self.reason,
            "notes": self.notes,
            "duration": self.duration_minutes,
            "medicalFiles": [file.dict() for file in self.medical_files],
        }


class ProviderAvailability(BaseModel):
    """Provider availability model"""

    provider_id: str
    provider_type: ProviderType
    weekly_schedule: Dict[str, List[Dict[str, Any]]]  # Day -> list of time slots
    exceptions: List[Dict[str, Any]]  # Special dates (holidays, time off)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


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
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WorkHours(BaseModel):
    """Work hours model for provider schedules"""

    start: int  # Hour of day (0-23)
    end: int  # Hour of day (0-23)
    break_start: Optional[int] = None  # Optional break start hour
    break_end: Optional[int] = None  # Optional break end hour


class ScheduleConfiguration(BaseModel):
    """Schedule configuration for a provider"""

    provider_id: str
    work_hours: Dict[str, WorkHours]  # Day of week (0-6) -> work hours


class ProviderSchedule(BaseModel):
    """Provider schedule model"""

    provider_id: str
    provider_name: Optional[str] = None
    provider_type: ProviderType
    work_hours: Dict[str, WorkHours]  # Day of week (0-6) -> work hours
    exceptions: List[Dict[str, Any]] = []  # Special dates (holidays, time off)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


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
    days_of_week: Optional[List[int]] = None  # 0-6 for weekly recurrence
    day_of_month: Optional[int] = None  # 1-31 for monthly recurrence
    notes: Optional[str] = None
    virtual: bool = False


class PaginatedAppointmentResponse(BaseModel):
    """Paginated response model for appointments"""

    items: List[Appointment]
    total: int
    page: int
    limit: int
    pages: int

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

    def to_json(self) -> Dict[str, Any]:
        """Convert to format expected by frontend"""
        return {
            "items": [item.to_json() for item in self.items],
            "total": self.total,
            "page": self.page,
            "limit": self.limit,
            "pages": self.pages,
        }
