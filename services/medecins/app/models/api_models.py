from pydantic import BaseModel, EmailStr


class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    specialty: str | None = ""
    phone: str | None = ""
    address: str | None = ""


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
    submitted_at: str | None = None
    verified_at: str | None = None
    license_number: str | None = None
    license_authority: str | None = None
    license_expiry: str | None = None
    rejected_reason: str | None = None


class UpdateProfileResponse(BaseModel):
    message: str
    profile: dict


class VerifyDoctorRequest(BaseModel):
    license_number: str
    license_authority: str
    license_expiry: str
    submitted_at: str
    documents: list[str] = []


class VerifyDoctorResponse(BaseModel):
    message: str
    status: str
    submitted_at: str


class ScanVisitCardRequest(BaseModel):
    image: str  # Base64 encoded image


class ScanVisitCardResponse(BaseModel):
    extracted_info: dict
    raw_text: str


# Doctor list response model
class DoctorListItem(BaseModel):
    id: str
    name: str
    email: str
    specialty: str
    phone: str | None = None
    address: str | None = None
    profile_picture: str | None = None
    is_verified: bool | None = False
    bio: str | None = None
    license_number: str | None = None
    hospital: str | None = None
    education: str | None = None
    experience: str | None = None


class DoctorListResponse(BaseModel):
    items: list[DoctorListItem]
    total: int
    page: int
    pages: int


# Models for prescriptions
class MedicationItem(BaseModel):
    name: str
    dosage: str
    frequency: str
    duration: str
    instructions: str | None = None


class PrescriptionCreate(BaseModel):
    patient_id: str
    patient_name: str
    medications: list[MedicationItem]
    notes: str | None = None


class PrescriptionResponse(BaseModel):
    id: str
    doctor_id: str
    doctor_name: str
    patient_id: str
    patient_name: str
    medications: list[MedicationItem]
    notes: str | None = None
    status: str
    created_at: str
    expires_at: str | None = None
    dispensed_at: str | None = None
    cancelled_at: str | None = None
    renewal_of: str | None = None


class PrescriptionListResponse(BaseModel):
    items: list[PrescriptionResponse]
    total: int
    page: int
    pages: int


# Models for appointments
class AppointmentResponse(BaseModel):
    id: str
    doctor_id: str
    doctor_name: str | None = None
    patient_id: str
    patient_name: str | None = None
    requested_time: str
    status: str
    reason: str | None = None
    notes: str | None = None
    created_at: str
    updated_at: str | None = None


class AppointmentListResponse(BaseModel):
    items: list[AppointmentResponse]
    total: int
    page: int
    pages: int


# New models for radiology functionality
class RadiologyImage(BaseModel):
    id: str | None = None
    url: str
    type: str
    uploaded_at: str | None = None


class RadiologyReportResponse(BaseModel):
    id: str
    patient_id: str
    patient_name: str
    doctor_id: str | None = None
    doctor_name: str | None = None
    radiologist_id: str | None = None
    radiologist_name: str | None = None
    exam_type: str
    report_type: str
    content: str
    findings: str | None = None
    conclusion: str | None = None
    images: list[RadiologyImage] | None = None
    status: str
    created_at: str
    updated_at: str | None = None


class RadiologyReportsListResponse(BaseModel):
    items: list[RadiologyReportResponse]
    total: int
    page: int
    pages: int


class RadiologyExaminationRequest(BaseModel):
    patient_id: str
    patient_name: str
    exam_type: str
    reason: str | None = None
    urgency: str = "normal"  # normal, urgent, emergency


class RadiologyExaminationResponse(BaseModel):
    request_id: str
    doctor_id: str
    patient_id: str
    patient_name: str
    exam_type: str
    reason: str | None = None
    urgency: str
    status: str
    created_at: str


class RadiologyRequestModel(BaseModel):
    patient_id: str
    patient_name: str
    exam_type: str
    reason: str | None = None
    urgency: str = "normal"
