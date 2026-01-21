from typing import Any

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
    phone: str | None = None
    address: str | None = None
    profile_picture: str | None = None
    is_verified: bool | None = False
    verification_details: dict[str, Any] | None = None
    signature: str | None = None


class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    specialty: str
    phone: str
    address: str | None = None
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    newPassword: str


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class TokenRefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    detail: str


class VerifyRadiologueRequest(BaseModel):
    image: str  # Base64 encoded image


class VerifyRadiologueResponse(BaseModel):
    verified: bool
    message: str | None = None
    error: str | None = None
    debug_info: dict[str, Any] | None = None


class ScanVisitCardRequest(BaseModel):
    image: str  # Base64 encoded image


class ScanVisitCardResponse(BaseModel):
    name: str
    email: str
    specialty: str
    phone: str


class ReportRequest(BaseModel):
    patientName: str
    examType: str
    reportType: str
    content: str


# New models for improved service intercommunication


class RadiologyImage(BaseModel):
    id: str | None = None
    url: str
    type: str
    uploaded_at: str | None = None


class RadiologyReportRequest(BaseModel):
    patient_id: str
    patient_name: str
    doctor_id: str | None = None
    doctor_name: str | None = None
    exam_type: str
    report_type: str
    content: str
    findings: str | None = None
    conclusion: str | None = None
    images: list[RadiologyImage] | None = None


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
    doctor_id: str
    patient_id: str
    patient_name: str
    exam_type: str
    reason: str | None = None
    urgency: str = "normal"  # normal, urgent, emergency
