from typing import Dict, List, Optional

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    token: str
    id: str
    name: str
    email: EmailStr
    specialty: str
    phone_number: Optional[str] = ""
    address: Optional[str] = ""
    profile_image: Optional[str] = None
    is_verified: Optional[bool] = False
    verification_details: Optional[Dict] = None
    signature: Optional[str] = None


class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    specialty: str
    phoneNumber: str
    address: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    newPassword: str


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    error: str


class UpdateSignatureRequest(BaseModel):
    signature: str


class VerifyDoctorRequest(BaseModel):
    image: str  # Base64 encoded image


class VerifyDoctorResponse(BaseModel):
    verified: bool
    message: Optional[str] = None
    error: Optional[str] = None
    debug_info: Optional[Dict] = None


class ScanVisitCardRequest(BaseModel):
    image: str  # Base64 encoded image


class ScanVisitCardResponse(BaseModel):
    name: Optional[str] = ""
    email: Optional[str] = ""
    specialty: Optional[str] = ""
    phone_number: Optional[str] = ""


# Models for prescriptions
class MedicationItem(BaseModel):
    name: str
    dosage: str
    frequency: str
    duration: str
    instructions: Optional[str] = None


class PrescriptionCreate(BaseModel):
    patient_id: str
    patient_name: str
    medications: List[MedicationItem]
    notes: Optional[str] = None


class PrescriptionResponse(BaseModel):
    id: str
    doctor_id: str
    doctor_name: str
    patient_id: str
    patient_name: str
    medications: List[MedicationItem]
    notes: Optional[str] = None
    status: str
    created_at: str
    expires_at: Optional[str] = None
    dispensed_at: Optional[str] = None
    cancelled_at: Optional[str] = None
    renewal_of: Optional[str] = None


class PrescriptionListResponse(BaseModel):
    items: List[PrescriptionResponse]
    total: int
    page: int
    pages: int


# Models for appointments
class AppointmentResponse(BaseModel):
    id: str
    doctor_id: str
    doctor_name: Optional[str] = None
    patient_id: str
    patient_name: Optional[str] = None
    requested_time: str
    status: str
    reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None


class AppointmentListResponse(BaseModel):
    items: List[AppointmentResponse]
    total: int
    page: int
    pages: int


# New models for radiology functionality
class RadiologyImage(BaseModel):
    id: Optional[str] = None
    url: str
    type: str
    uploaded_at: Optional[str] = None


class RadiologyReportResponse(BaseModel):
    id: str
    patient_id: str
    patient_name: str
    doctor_id: Optional[str] = None
    doctor_name: Optional[str] = None
    radiologist_id: Optional[str] = None
    radiologist_name: Optional[str] = None
    exam_type: str
    report_type: str
    content: str
    findings: Optional[str] = None
    conclusion: Optional[str] = None
    images: Optional[List[RadiologyImage]] = None
    status: str
    created_at: str
    updated_at: Optional[str] = None


class RadiologyReportsListResponse(BaseModel):
    items: List[RadiologyReportResponse]
    total: int
    page: int
    pages: int


class RadiologyExaminationRequest(BaseModel):
    patient_id: str
    patient_name: str
    exam_type: str
    reason: Optional[str] = None
    urgency: str = "normal"  # normal, urgent, emergency


class RadiologyExaminationResponse(BaseModel):
    request_id: str
    doctor_id: str
    patient_id: str
    patient_name: str
    exam_type: str
    reason: Optional[str] = None
    urgency: str
    status: str
    created_at: str


class RadiologyRequestModel(BaseModel):
    patient_id: str
    patient_name: str
    exam_type: str
    reason: Optional[str] = None
    urgency: str = "normal"
