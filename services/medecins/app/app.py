import base64
import io
import os
import random
import re
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from typing import Dict
import uvicorn
import jwt
import pytesseract
from auth.keycloak_auth import get_current_user
from bson import ObjectId
from decorator.health_check import health_check_middleware
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from models.api_models import (ErrorResponse, ForgotPasswordRequest,
                               LoginRequest, LoginResponse, MessageResponse,
                               ResetPasswordRequest, ScanVisitCardRequest,
                               ScanVisitCardResponse, SignupRequest,
                               UpdateSignatureRequest, VerifyDoctorRequest,
                               VerifyDoctorResponse, VerifyOTPRequest)
from models.doctor import Doctor, DoctorInDB, DoctorUpdate, PasswordChange
from PIL import Image
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
    title="MedApp Doctors Service",
    description="API for managing doctor profiles and authentication",
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



def send_otp_email(to_email, otp):
    try:
        sender_email = os.getenv("EMAIL_ADDRESS")
        sender_password = os.getenv("EMAIL_PASSWORD")

        logger_service.debug(
            f"Email configuration - Sender: {sender_email}, Password length: {len(sender_password) if sender_password else 0}"
        )

        if not sender_email or not sender_password:
            logger_service.error("Email configuration missing")
            raise Exception("Email configuration missing")

        msg = MIMEText(
            f"""
        Hello,

        Your OTP code for password reset is: {otp}

        This code will expire in 15 minutes.
        If you did not request this code, please ignore this email.

        Best regards,
        Medicare Team
        """
        )

        msg["Subject"] = "Medicare - Password Reset OTP"
        msg["From"] = sender_email
        msg["To"] = to_email

        try:
            logger_service.debug("Attempting SMTP connection to smtp.gmail.com:465")
            smtp = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10)
            logger_service.debug("SMTP connection successful")

            logger_service.debug("Attempting SMTP login")
            smtp.login(sender_email, sender_password)
            logger_service.debug("SMTP login successful")

            logger_service.debug("Sending email")
            smtp.send_message(msg)
            logger_service.debug("Email sent successfully")

            smtp.quit()
            return True

        except smtplib.SMTPAuthenticationError as auth_error:
            logger_service.error(
                f"SMTP Authentication failed - Details: {str(auth_error)}"
            )
            raise Exception(
                f"Email authentication failed. Please check your credentials."
            )

        except smtplib.SMTPException as smtp_error:
            logger_service.error(f"SMTP error occurred: {str(smtp_error)}")
            raise Exception(f"Email sending failed: {str(smtp_error)}")

        except Exception as e:
            logger_service.error(f"Unexpected SMTP error: {str(e)}")
            raise Exception(f"Unexpected error while sending email: {str(e)}")

    except Exception as e:
        logger_service.error(f"Email sending error: {str(e)}")
        return False


@app.post(
    "/api/signup",
    response_model=DoctorInDB,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}},
)
async def signup(request: SignupRequest):
    if mongodb_client.db.doctors.find_one({"email": request.email}):
        raise HTTPException(status_code=400, detail="Email already registered")

    doctor = Doctor(
        name=request.name,
        email=request.email,
        specialty=request.specialty,
        phone_number=request.phoneNumber,
        address=request.address,
        password=request.password,
    )

    # Insert the doctor document with is_verified field
    result = mongodb_client.db.doctors.insert_one(
        {
            "_id": doctor._id,
            "name": doctor.name,
            "email": doctor.email,
            "password_hash": doctor.password_hash,
            "specialty": doctor.specialty,
            "phone_number": doctor.phone_number,
            "address": doctor.address,
            "is_verified": False,  # Add default verification status
        }
    )

    # Convert to Pydantic model for response
    return doctor.to_pydantic()


@app.post(
    "/api/login",
    response_model=LoginResponse,
    responses={401: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def login(request: LoginRequest):
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

            # Include verification status and details in response
            return LoginResponse(
                token=token,
                id=str(doctor_data["_id"]),
                name=doctor_data["name"],
                email=doctor_data["email"],
                specialty=doctor_data["specialty"],
                phone_number=doctor_data.get("phone_number", ""),
                address=doctor_data.get("address", ""),
                profile_image=doctor_data.get("profile_image"),
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


@app.post(
    "/api/forgot-password",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def forgot_password(request: ForgotPasswordRequest):
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


@app.post(
    "/api/verify-otp",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}},
)
async def verify_otp(request: VerifyOTPRequest):
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


@app.post(
    "/api/reset-password",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def reset_password(request: ResetPasswordRequest):
    doctor_data = mongodb_client.db.doctors.find_one(
        {
            "email": request.email,
            "reset_otp": request.otp,
            "otp_expiry": {"$gt": datetime.utcnow()},
        }
    )

    if not doctor_data:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    # Create a Doctor instance and set the new password
    doctor = Doctor.from_dict(doctor_data)
    doctor.set_password(request.newPassword)

    # Update the password hash and remove the OTP data
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


@app.get(
    "/api/profile", response_model=DoctorInDB, responses={404: {"model": ErrorResponse}}
)
async def get_profile(user_info: Dict = Depends(get_current_user)):
    user_id = user_info.get("user_id")
    doctor_data = mongodb_client.db.doctors.find_one({"_id": ObjectId(user_id)})
    if not doctor_data:
        raise HTTPException(status_code=404, detail="Doctor not found")

    # Create a Doctor instance
    doctor = Doctor.from_dict(doctor_data)
    doctor.password_hash = doctor_data.get("password_hash")

    # Add additional fields from the database
    doctor.is_verified = doctor_data.get("is_verified", False)
    doctor.verification_details = doctor_data.get("verification_details")
    doctor.signature = doctor_data.get("signature")

    return doctor.to_pydantic()


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
    password_data: PasswordChange, user_info: Dict = Depends(get_current_user)
):
    user_id = user_info.get("user_id")
    doctor_data = mongodb_client.db.doctors.find_one({"_id": ObjectId(user_id)})
    if not doctor_data:
        raise HTTPException(status_code=404, detail="Doctor not found")

    doctor = Doctor.from_dict(doctor_data)
    doctor.password_hash = doctor_data["password_hash"]

    if not doctor.check_password(password_data.current_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    # Set and hash the new password
    doctor.set_password(password_data.new_password)

    # Update the password hash in the database
    result = mongodb_client.db.doctors.update_one(
        {"_id": ObjectId(user_id)}, {"$set": {"password_hash": doctor.password_hash}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Failed to update password")

    return {"message": "Password updated successfully"}


@app.put(
    "/api/update-profile",
    response_model=DoctorInDB,
    responses={404: {"model": ErrorResponse}},
)
async def update_profile(
    update_data: DoctorUpdate, user_info: Dict = Depends(get_current_user)
):
    user_id = user_info.get("user_id")

    # Get current doctor data to preserve verification status
    current_doctor = mongodb_client.db.doctors.find_one({"_id": ObjectId(user_id)})
    if not current_doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    # Prepare update fields, only include non-None values
    update_fields = {}
    for field, value in update_data.dict(exclude_unset=True).items():
        if value is not None:
            update_fields[field] = value

    # Update database
    mongodb_client.db.doctors.update_one(
        {"_id": ObjectId(user_id)}, {"$set": update_fields}
    )

    # Get updated doctor data
    updated_doctor = mongodb_client.db.doctors.find_one({"_id": ObjectId(user_id)})
    doctor = Doctor.from_dict(updated_doctor)

    # Add additional fields
    doctor.is_verified = updated_doctor.get("is_verified", False)
    doctor.verification_details = updated_doctor.get("verification_details")
    doctor.profile_image = updated_doctor.get("profile_image")
    doctor.signature = updated_doctor.get("signature")

    return doctor.to_pydantic()


@app.post("/api/logout", response_model=MessageResponse)
async def logout(user_info: Dict = Depends(get_current_user)):
    # Optionally blacklist or track tokens here if desired
    return {"message": "Logged out successfully"}


@app.post(
    "/api/scan-visit-card",
    response_model=ScanVisitCardResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def scan_visit_card(request: ScanVisitCardRequest):
    if not request.image:
        raise HTTPException(status_code=400, detail="No image provided")

    try:
        # Decode base64 image
        image = Image.open(io.BytesIO(base64.b64decode(request.image)))

        # Perform OCR using pytesseract
        text = pytesseract.image_to_string(image)

        # Extract relevant information
        name = extract_name(text)
        email = extract_email(text)
        specialty = extract_specialty(text)
        phone = extract_phone_number(text)

        return ScanVisitCardResponse(
            name=name,
            email=email,
            specialty=specialty,
            phone_number=phone,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/api/verify-doctor",
    response_model=VerifyDoctorResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def verify_doctor(
    request: VerifyDoctorRequest, user_info: Dict = Depends(get_current_user)
):
    try:
        user_id = user_info.get("user_id")
        image_data = request.image

        if not image_data:
            raise HTTPException(status_code=400, detail="No image provided")

        # Get doctor's data from database
        doctor_data = mongodb_client.db.doctors.find_one({"_id": ObjectId(user_id)})
        if not doctor_data:
            raise HTTPException(status_code=404, detail="Doctor not found")

        # Get doctor's name from database
        doctor_name = doctor_data["name"].lower().strip()

        logger_service.debug(f"Checking for Name='{doctor_name}'")

        # Process the image
        image = Image.open(io.BytesIO(base64.b64decode(image_data)))

        # Enhance image quality for better OCR
        image = image.convert("L")  # Convert to grayscale
        image = image.point(lambda x: 0 if x < 128 else 255, "1")  # Enhance contrast

        # Extract text from image
        extracted_text = pytesseract.image_to_string(image)
        extracted_text = extracted_text.lower().strip()

        logger_service.debug(f"Extracted text: {extracted_text}")

        # Simple text matching for name
        name_found = doctor_name in extracted_text

        # If name has multiple parts, check each part
        if not name_found:
            name_parts = doctor_name.split()
            name_found = all(part in extracted_text for part in name_parts)

        logger_service.debug(f"Name found: {name_found}")

        if name_found:
            # Update verification status
            result = mongodb_client.db.doctors.update_one(
                {"_id": ObjectId(user_id)},
                {
                    "$set": {
                        "is_verified": True,
                        "verification_details": {
                            "verified_at": datetime.utcnow(),
                            "matched_text": extracted_text,
                        },
                    }
                },
            )

            if result.modified_count > 0:
                return VerifyDoctorResponse(
                    verified=True, message="Name verification successful"
                )
            else:
                raise HTTPException(
                    status_code=500, detail="Failed to update verification status"
                )
        else:
            return VerifyDoctorResponse(
                verified=False,
                error="Verification failed: name not found in document",
                debug_info={
                    "name_found": name_found,
                    "doctor_name": doctor_name,
                },
            )

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Verification error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")


# Extraction functions
def extract_name(text):
    # Look for patterns that might indicate a name
    # Usually names appear at the beginning or after "Dr." or similar titles
    lines = text.split("\n")
    for line in lines:
        # Look for "Dr." or similar titles
        name_match = re.search(
            r"(?:Dr\.?|Doctor)\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", line, re.IGNORECASE
        )
        if name_match:
            return name_match.group(1)

        # Look for capitalized words that might be names
        name_match = re.search(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", line)
        if name_match:
            return name_match.group(1)
    return ""


def extract_email(text):
    # Implement logic to extract email from text
    email_match = re.search(r"[\w\.-]+@[\w\.-]+", text)
    if email_match:
        return email_match.group(0)
    return "Extracted Email"


def extract_specialty(text):
    # Common medical specialties
    specialties = [
        "Cardiology",
        "Dermatology",
        "Neurology",
        "Pediatrics",
        "Oncology",
        "Orthopedics",
        "Gynecology",
        "Psychiatry",
        "Surgery",
        "Internal Medicine",
        # Add more specialties as needed
    ]

    lines = text.split("\n")
    for line in lines:
        # Check for known specialties
        for specialty in specialties:
            if specialty.lower() in line.lower():
                return line.strip()

        # Look for patterns that might indicate a specialty
        specialty_match = re.search(
            r"(?:Specialist|Consultant)\s+in\s+([A-Za-z\s]+)", line
        )
        if specialty_match:
            return specialty_match.group(1).strip()
    return ""


def extract_phone_number(text):
    # Basic pattern to match phone formats, can be refined
    phone_match = re.search(r"(\+?\d[\d\s\-]{7,}\d)", text)
    if phone_match:
        return phone_match.group(0).strip()
    return "Extracted Phone"


@app.post(
    "/api/update-signature",
    response_model=dict,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def update_signature(
    request: UpdateSignatureRequest, user_info: Dict = Depends(get_current_user)
):
    try:
        user_id = user_info.get("user_id")
        signature = request.signature

        if not signature:
            raise HTTPException(status_code=400, detail="No signature provided")

        result = mongodb_client.db.doctors.update_one(
            {"_id": ObjectId(user_id)}, {"$set": {"signature": signature}}
        )

        if result.modified_count > 0:
            # Get updated doctor data
            doctor_data = mongodb_client.db.doctors.find_one({"_id": ObjectId(user_id)})
            return {
                "message": "Signature updated successfully",
                "signature": doctor_data.get("signature"),
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to update signature")

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Signature update error: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Signature update failed: {str(e)}"
        )


if __name__ == "__main__":
    uvicorn.run("app:app", host=Config.HOST, port=Config.PORT, reload=True)