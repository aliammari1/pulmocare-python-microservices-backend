from enum import Enum

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
    name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    preferred_username: str | None = None
    role: Role | None = None


class TokenRequest(BaseModel):
    token: str


class TokenVerifyResponse(BaseModel):
    valid: bool
    user_id: str | None = None
    email: str | None = None
    name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    preferred_username: str | None = None
    email_verified: bool | None = None
    roles: list[str] | None = None  # Changed from List[Role] to List[str] to accept string values
    resource_access: dict | None = None
    primary_role: Role | None = None
    expires_at: int | None = None
    issued_at: int | None = None
    issuer: str | None = None
    token_type: str | None = None
    session_id: str | None = None
    scope: list[str] | None = None
    error: str | None = None


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
    username: str | None = None
    phone: str | None = None
    specialty: str | None = None
    address: str | None = None
    role: Role | None = None
    bio: str | None = None
    license_number: str | None = None
    hospital: str | None = None
    education: str | None = None
    experience: str | None = None
    signature: str | None = None
    is_verified: bool | None = False
    verification_details: dict | None = None
    date_of_birth: str | None = None
    blood_type: str | None = None
    social_security_number: str | None = None
    medical_history: list[str] | None = None
    allergies: list[str] | None = None
    height: float | None = None
    weight: float | None = None
    medical_files: list[str] | None = None


class RegisterResponse(BaseModel):
    message: str
    user_id: str
    access_token: str | None = None
    refresh_token: str | None = None
    expires_in: int | None = None


class LogoutRequest(BaseModel):
    refresh_token: str


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    error: str
    details: str | None = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr
