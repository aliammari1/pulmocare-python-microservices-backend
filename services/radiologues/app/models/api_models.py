from typing import Any, Dict, Optional

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
    phone_number: Optional[str] = None
    address: Optional[str] = None
    profile_image: Optional[str] = None
    is_verified: Optional[bool] = False
    verification_details: Optional[Dict[str, Any]] = None
    signature: Optional[str] = None


class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    specialty: str
    phoneNumber: str
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
    phone_number: str


class ReportRequest(BaseModel):
    patientName: str
    examType: str
    reportType: str
    content: str
