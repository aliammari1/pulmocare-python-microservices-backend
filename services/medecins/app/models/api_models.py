from typing import Dict, Optional

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
