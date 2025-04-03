import os
from datetime import datetime, timedelta
from typing import Dict
import uvicorn
import jwt
import random
from auth.keycloak_auth import get_current_patient
from bson import ObjectId
from decorator.health_check import health_check_middleware
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from models.patient_model import (ErrorResponse, ForgotPasswordRequest,
                                  LoginRequest, LoginResponse, MessageResponse,
                                  PasswordChange, Patient, PatientCreate,
                                  PatientInDB, PatientUpdate,
                                  ResetPasswordRequest, VerifyOTPRequest)
from services.logger_service import logger_service
from services.mongodb_client import MongoDBClient
from services.rabbitmq_client import RabbitMQClient
from services.redis_client import RedisClient
from services.tracing_service import TracingService

from config import Config

# Determine environment and load corresponding .env file
env = os.getenv("ENV", "development")
dotenv_file = f".env.{env}"
if not os.path.exists(dotenv_file):
    dotenv_file = ".env"
load_dotenv(dotenv_path=dotenv_file)

# Initialize FastAPI app
app = FastAPI(
    title="MedApp Patients Service",
    description="API for managing patient profiles and authentication",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update with specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Apply health check middleware
app = health_check_middleware(Config)(app)

# Initialize services
tracing_service = TracingService(app)
redis_client = RedisClient(Config)
mongodb_client = MongoDBClient(Config)
rabbitmq_client = RabbitMQClient(Config)



@app.post(
    "/api/signup",
    response_model=PatientInDB,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}},
)
async def signup(request: PatientCreate):
    if mongodb_client.db.patients.find_one({"email": request.email}):
        raise HTTPException(status_code=400, detail="Email already registered")

    patient = Patient(
        name=request.name,
        email=request.email,
        phone_number=request.phone_number,
        address=request.address,
        date_of_birth=request.date_of_birth,
        password=request.password,
    )

    # Insert the patient document
    result = mongodb_client.db.patients.insert_one(
        {
            "_id": patient._id,
            "name": patient.name,
            "email": patient.email,
            "password_hash": patient.password_hash,
            "phone_number": patient.phone_number,
            "address": patient.address,
            "date_of_birth": patient.date_of_birth,
            "created_at": datetime.utcnow(),
        }
    )

    # Convert to Pydantic model for response
    return patient.to_pydantic()


@app.post(
    "/api/login",
    response_model=LoginResponse,
    responses={401: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def login(request: LoginRequest):
    try:
        logger_service.debug(f"Login attempt for email: {request.email}")

        patient_data = mongodb_client.db.patients.find_one({"email": request.email})
        if not patient_data:
            logger_service.debug("Email not found")
            raise HTTPException(status_code=401, detail="Invalid credentials")

        patient = Patient.from_dict(patient_data)
        patient.password_hash = patient_data["password_hash"]

        if patient.check_password(request.password):
            token = jwt.encode(
                {
                    "user_id": str(patient_data["_id"]),
                    "exp": datetime.utcnow() + timedelta(days=1),
                },
                Config.JWT_SECRET_KEY,
                algorithm="HS256",
            )

            return LoginResponse(
                token=token,
                id=str(patient_data["_id"]),
                name=patient_data["name"],
                email=patient_data["email"],
                phone_number=patient_data.get("phone_number", ""),
                address=patient_data.get("address", ""),
                date_of_birth=patient_data.get("date_of_birth"),
                profile_image=patient_data.get("profile_image"),
            )
        else:
            logger_service.debug("Invalid password")
            raise HTTPException(status_code=401, detail="Invalid credentials")

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Login error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@app.post(
    "/api/forgot-password",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def forgot_password(request: ForgotPasswordRequest):
    try:
        email = request.email
        logger_service.debug(f"Forgot password request received for email: {email}")

        patient_data = mongodb_client.db.patients.find_one({"email": email})
        if not patient_data:
            logger_service.debug(f"Email not found: {email}")
            raise HTTPException(status_code=404, detail="Email not found")

        # Generate OTP
        otp = "".join([str(random.randint(0, 9)) for _ in range(6)])
        logger_service.debug(f"Generated OTP: {otp}")

        # Store OTP in database with expiry
        mongodb_client.db.patients.update_one(
            {"email": email},
            {
                "$set": {
                    "reset_otp": otp,
                    "otp_expiry": datetime.utcnow() + timedelta(minutes=15),
                }
            },
        )

        # In a real application, you would send the OTP via email or SMS
        logger_service.debug("OTP stored successfully")
        return {"message": "If your email is registered, you will receive a reset code"}

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Unexpected error in forgot_password: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"An unexpected error occurred: {str(e)}"
        )


@app.post(
    "/api/verify-otp",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}},
)
async def verify_otp(request: VerifyOTPRequest):
    result = mongodb_client.db.patients.find_one(
        {
            "email": request.email,
            "reset_otp": request.otp,
            "otp_expiry": {"$gt": datetime.utcnow()},
        }
    )

    if not result:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    return {"message": "OTP verified successfully"}


@app.post(
    "/api/reset-password",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def reset_password(request: ResetPasswordRequest):
    patient_data = mongodb_client.db.patients.find_one(
        {
            "email": request.email,
            "reset_otp": request.otp,
            "otp_expiry": {"$gt": datetime.utcnow()},
        }
    )

    if not patient_data:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    # Create a Patient instance and set the new password
    patient = Patient.from_dict(patient_data)
    patient.set_password(request.new_password)

    # Update the password hash and remove the OTP data
    result = mongodb_client.db.patients.update_one(
        {"email": request.email},
        {
            "$set": {"password_hash": patient.password_hash},
            "$unset": {"reset_otp": "", "otp_expiry": ""},
        },
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Failed to update password")

    return {"message": "Password reset successful"}


@app.get(
    "/api/profile",
    response_model=PatientInDB,
    responses={404: {"model": ErrorResponse}},
)
async def get_profile(user_info: Dict = Depends(get_current_patient)):
    user_id = user_info.get("user_id")
    patient_data = mongodb_client.db.patients.find_one({"_id": ObjectId(user_id)})
    if not patient_data:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Create a Patient instance
    patient = Patient.from_dict(patient_data)
    patient.password_hash = patient_data.get("password_hash")

    return patient.to_pydantic()


@app.put(
    "/api/update-profile",
    response_model=PatientInDB,
    responses={404: {"model": ErrorResponse}},
)
async def update_profile(
    update_data: PatientUpdate, user_info: Dict = Depends(get_current_patient)
):
    user_id = user_info.get("user_id")

    # Get current patient data
    current_patient = mongodb_client.db.patients.find_one({"_id": ObjectId(user_id)})
    if not current_patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Prepare update fields, only include non-None values
    update_fields = {}
    for field, value in update_data.dict(exclude_unset=True).items():
        if value is not None:
            update_fields[field] = value

    # Update database
    mongodb_client.db.patients.update_one(
        {"_id": ObjectId(user_id)}, {"$set": update_fields}
    )

    # Get updated patient data
    updated_patient = mongodb_client.db.patients.find_one({"_id": ObjectId(user_id)})
    patient = Patient.from_dict(updated_patient)

    return patient.to_pydantic()


@app.post(
    "/api/change-password",
    response_model=MessageResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def change_password(
    password_data: PasswordChange, user_info: Dict = Depends(get_current_patient)
):
    user_id = user_info.get("user_id")
    patient_data = mongodb_client.db.patients.find_one({"_id": ObjectId(user_id)})
    if not patient_data:
        raise HTTPException(status_code=404, detail="Patient not found")

    patient = Patient.from_dict(patient_data)
    patient.password_hash = patient_data["password_hash"]

    if not patient.check_password(password_data.current_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    # Set and hash the new password
    patient.set_password(password_data.new_password)

    # Update the password hash in the database
    result = mongodb_client.db.patients.update_one(
        {"_id": ObjectId(user_id)}, {"$set": {"password_hash": patient.password_hash}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Failed to update password")

    return {"message": "Password updated successfully"}


@app.post("/api/logout", response_model=MessageResponse)
async def logout(user_info: Dict = Depends(get_current_patient)):
    # Optionally blacklist or track tokens here if desired
    return {"message": "Logged out successfully"}

if __name__ == "__main__":
    uvicorn.run("app:app", host=Config.HOST, port=Config.PORT, reload=True)