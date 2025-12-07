from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, EmailStr


class Role(str, Enum):
    ADMIN = "admin"
    DOCTOR = "doctor"
    PATIENT = "patient"
    RADIOLOGIST = "radiologist"


class HealthCheckResponse(BaseModel):
    status: str
    service: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user_id: str
    email: str
    name: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    preferred_username: Optional[str] = None
    role: Optional[Role] = None


class TokenRequest(BaseModel):
    token: str


class TokenVerifyResponse(BaseModel):
    valid: bool
    user_id: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    preferred_username: Optional[str] = None
    email_verified: Optional[bool] = None
    roles: Optional[List[str]] = (
        None  # Changed from List[Role] to List[str] to accept string values
    )
    resource_access: Optional[Dict] = None
    primary_role: Optional[Role] = None
    expires_at: Optional[int] = None
    issued_at: Optional[int] = None
    issuer: Optional[str] = None
    token_type: Optional[str] = None
    session_id: Optional[str] = None
    scope: Optional[List[str]] = None
    error: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    username: Optional[str] = None
    phone: Optional[str] = None
    specialty: Optional[str] = None
    address: Optional[str] = None
    role: Optional[Role] = None
    bio: Optional[str] = None
    license_number: Optional[str] = None
    hospital: Optional[str] = None
    education: Optional[str] = None
    experience: Optional[str] = None
    signature: Optional[str] = None
    is_verified: Optional[bool] = False
    verification_details: Optional[Dict] = None
    date_of_birth: Optional[str] = None
    blood_type: Optional[str] = None
    social_security_number: Optional[str] = None
    medical_history: Optional[List[str]] = None
    allergies: Optional[List[str]] = None
    height: Optional[float] = None
    weight: Optional[float] = None
    medical_files: Optional[List[str]] = None


class RegisterResponse(BaseModel):
    message: str
    user_id: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None


class LogoutRequest(BaseModel):
    refresh_token: str


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    error: str
    details: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr
