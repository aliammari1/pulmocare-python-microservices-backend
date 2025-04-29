from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict
from datetime import datetime, timedelta
import random
import jwt
from bson import ObjectId

from models.api_models import (
    ErrorResponse, ForgotPasswordRequest, LoginRequest, LoginResponse,
    MessageResponse, ResetPasswordRequest, SignupRequest, VerifyOTPRequest
)
from models.doctor import Doctor, DoctorInDB, PasswordChange
from services.mongodb_client import MongoDBClient
from services.redis_client import RedisClient
from services.logger_service import logger_service
from config import Config
from auth.keycloak_auth import get_current_user
from services.doctor_service import send_otp_email

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

mongodb_client = MongoDBClient(Config)


@router.post(
    "/signup",
    response_model=DoctorInDB,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}},
)
async def signup(request: SignupRequest):
    """
    Register a new doctor account.
    """
    if mongodb_client.db.doctors.find_one({"email": request.email}):
        raise HTTPException(status_code=400, detail="Email already registered")

    doctor = Doctor(
        name=request.name,
        email=request.email,
        specialty=request.specialty,
        phone=request.phone,
        address=request.address,
        password=request.password,
    )

    mongodb_client.db.doctors.insert_one(
        {
            "_id": doctor._id,
            "name": doctor.name,
            "email": doctor.email,
            "password_hash": doctor.password_hash,
            "specialty": doctor.specialty,
            "phone": doctor.phone,
            "address": doctor.address,
            "is_verified": False,
        }
    )

    return doctor.to_pydantic()

@router.post(
    "/login",
    response_model=LoginResponse,
    responses={401: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def login(request: LoginRequest):
    """
    Authenticate a doctor and return a JWT token.
    """
    try:
        logger_service.debug(f"Login attempt for email: {request.email}")

        doctor_data = mongodb_client.db.doctors.find_one({"email": request.email})
        if not doctor_data:
            logger_service.debug("Email not found")
            raise HTTPException(status_code=401, detail="Invalid credentials")

        doctor = Doctor.from_dict(doctor_data)
        doctor.password_hash = doctor_data["password_hash"]

        if doctor.check_password(request.password):
            token = jwt.encode(
                {
                    "user_id": str(doctor_data["_id"]),
                    "exp": datetime.utcnow() + timedelta(days=1),
                },
                Config.JWT_SECRET_KEY,
                algorithm="HS256",
            )

            return LoginResponse(
                token=token,
                id=str(doctor_data["_id"]),
                name=doctor_data["name"],
                email=doctor_data["email"],
                specialty=doctor_data["specialty"],
                phone=doctor_data.get("phone", ""),
                address=doctor_data.get("address", ""),
                profile_picture=doctor_data.get("profile_picture"),
                is_verified=doctor_data.get("is_verified", False),
                verification_details=doctor_data.get("verification_details", None),
                signature=doctor_data.get("signature"),
            )
        else:
            logger_service.debug("Invalid password")
            raise HTTPException(status_code=401, detail="Invalid credentials")

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Login error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def forgot_password(request: ForgotPasswordRequest):
    """
    Send an OTP to the doctor's email for password reset.
    """
    try:
        email = request.email
        logger_service.debug(f"Forgot password request received for email: {email}")

        doctor_data = mongodb_client.db.doctors.find_one({"email": email})
        if not doctor_data:
            logger_service.debug(f"Email not found: {email}")
            raise HTTPException(status_code=404, detail="Email not found")

        otp = str(random.randint(100000, 999999))
        logger_service.debug(f"Generated OTP: {otp}")

        if send_otp_email(email, otp):
            mongodb_client.db.doctors.update_one(
                {"email": email},
                {
                    "$set": {
                        "reset_otp": otp,
                        "otp_expiry": datetime.utcnow() + timedelta(minutes=15),
                    }
                },
            )
            logger_service.debug("OTP sent and saved successfully")
            return {"message": "OTP sent successfully"}
        else:
            logger_service.error("Failed to send OTP email")
            raise HTTPException(
                status_code=500, detail="Failed to send OTP. Please try again later."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Unexpected error in forgot_password: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"An unexpected error occurred: {str(e)}"
        )

@router.post(
    "/verify-otp",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}},
)
async def verify_otp(request: VerifyOTPRequest):
    """
    Verify the OTP sent to the doctor's email.
    """
    result = mongodb_client.db.doctors.find_one(
        {
            "email": request.email,
            "reset_otp": request.otp,
            "otp_expiry": {"$gt": datetime.utcnow()},
        }
    )

    if not result:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    return {"message": "OTP verified successfully"}

@router.post(
    "/reset-password",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def reset_password(request: ResetPasswordRequest):
    """
    Reset the doctor's password using a valid OTP.
    """
    doctor_data = mongodb_client.db.doctors.find_one(
        {
            "email": request.email,
            "reset_otp": request.otp,
            "otp_expiry": {"$gt": datetime.utcnow()},
        }
    )

    if not doctor_data:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    doctor = Doctor.from_dict(doctor_data)
    doctor.set_password(request.newPassword)

    result = mongodb_client.db.doctors.update_one(
        {"email": request.email},
        {
            "$set": {"password_hash": doctor.password_hash},
            "$unset": {"reset_otp": "", "otp_expiry": ""},
        },
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Failed to update password")

    return {"message": "Password reset successful"}

@router.post(
    "/change-password",
    response_model=MessageResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def change_password(
    password_data: PasswordChange, user_info: Dict = Depends(get_current_user)
):
    """
    Change the password for the currently authenticated doctor.
    """
    user_id = user_info.get("user_id")
    doctor_data = mongodb_client.db.doctors.find_one({"_id": ObjectId(user_id)})
    if not doctor_data:
        raise HTTPException(status_code=404, detail="Doctor not found")

    doctor = Doctor.from_dict(doctor_data)
    doctor.password_hash = doctor_data["password_hash"]

    if not doctor.check_password(password_data.current_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    doctor.set_password(password_data.new_password)

    result = mongodb_client.db.doctors.update_one(
        {"_id": ObjectId(user_id)}, {"$set": {"password_hash": doctor.password_hash}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Failed to update password")

    return {"message": "Password updated successfully"}

@router.post("/logout", response_model=MessageResponse)
async def logout(
    # user_info: Dict = Depends(get_current_user)
    ):
    """
    Logout the currently authenticated doctor.
    """
    return {"message": "Logged out successfully"}
