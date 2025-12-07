from typing import Dict, List, Optional

from pydantic import BaseModel, EmailStr


class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    specialty: Optional[str] = ""
    phone: Optional[str] = ""
    address: Optional[str] = ""


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class VerifyOTPRequest(BaseModel):
    user_id: str
    otp: str


class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    detail: str


class UpdateSignatureRequest(BaseModel):
    signature_data: str


class DoctorVerificationInfoResponse(BaseModel):
    status: str
    submitted_at: Optional[str] = None
    verified_at: Optional[str] = None
    license_number: Optional[str] = None
    license_authority: Optional[str] = None
    license_expiry: Optional[str] = None
    rejected_reason: Optional[str] = None


class UpdateProfileResponse(BaseModel):
    message: str
    profile: Dict


class VerifyDoctorRequest(BaseModel):
    license_number: str
    license_authority: str
    license_expiry: str
    submitted_at: str
    documents: List[str] = []


class VerifyDoctorResponse(BaseModel):
    message: str
    status: str
    submitted_at: str


class ScanVisitCardRequest(BaseModel):
    image: str  # Base64 encoded image


class ScanVisitCardResponse(BaseModel):
    extracted_info: Dict
    raw_text: str


# Doctor list response model
class DoctorListItem(BaseModel):
    id: str
    name: str
    email: str
    specialty: str
    phone: Optional[str] = None
    address: Optional[str] = None
    profile_picture: Optional[str] = None
    is_verified: Optional[bool] = False
    bio: Optional[str] = None
    license_number: Optional[str] = None
    hospital: Optional[str] = None
    education: Optional[str] = None
    experience: Optional[str] = None


class DoctorListResponse(BaseModel):
    items: List[DoctorListItem]
    total: int
    page: int
    pages: int


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
