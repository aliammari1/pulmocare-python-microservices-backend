from enum import Enum
from pydantic import BaseModel, EmailStr
from typing import Dict, List, Optional

class Role(str, Enum):
    ADMIN = "admin"
    DOCTOR = "doctor-role"
    PATIENT = "patient-role"
    RADIOLOGIST = "radiologist-role"


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
    roles: Optional[List[str]] = None
    resource_access: Optional[Dict] = None
    primary_role: Optional[str] = None
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
    # firstName: str
    # lastName: str
    name: str
    username: Optional[str] = None
    phone: Optional[str] = None
    specialty: Optional[str] = None
    address: Optional[str] = None
    role: Optional[str] = None


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

