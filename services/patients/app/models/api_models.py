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


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class TokenRefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


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


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    detail: str
