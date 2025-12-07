from typing import Any, Dict, List, Optional

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
    phone: Optional[str] = None
    address: Optional[str] = None
    profile_picture: Optional[str] = None
    is_verified: Optional[bool] = False
    verification_details: Optional[Dict[str, Any]] = None
    signature: Optional[str] = None


class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    specialty: str
    phone: str
    address: Optional[str] = None
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
    message: Optional[str] = None
    error: Optional[str] = None
    debug_info: Optional[Dict[str, Any]] = None


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
    id: Optional[str] = None
    url: str
    type: str
    uploaded_at: Optional[str] = None


class RadiologyReportRequest(BaseModel):
    patient_id: str
    patient_name: str
    doctor_id: Optional[str] = None
    doctor_name: Optional[str] = None
    exam_type: str
    report_type: str
    content: str
    findings: Optional[str] = None
    conclusion: Optional[str] = None
    images: Optional[List[RadiologyImage]] = None


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
    doctor_id: str
    patient_id: str
    patient_name: str
    exam_type: str
    reason: Optional[str] = None
    urgency: str = "normal"  # normal, urgent, emergency
