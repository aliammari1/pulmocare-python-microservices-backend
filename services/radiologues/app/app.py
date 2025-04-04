import base64
import io
import os
import random
import re
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from typing import Dict, List, Optional

import pytesseract
import requests
import uvicorn
from auth.jwt_auth import create_access_token, get_current_user
from bs4 import BeautifulSoup
from bson import ObjectId
from decorator.health_check import health_check_middleware
from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from models.api_models import (ErrorResponse, ForgotPasswordRequest,
                               LoginRequest, LoginResponse, MessageResponse,
                               RadiologyReportRequest, RadiologyReportResponse,
                               RadiologyReportsListResponse,
                               ResetPasswordRequest, ScanVisitCardRequest,
                               ScanVisitCardResponse, SignupRequest,
                               VerifyOTPRequest, VerifyRadiologueRequest,
                               VerifyRadiologueResponse)
from models.radiologue import Radiologue
from PIL import Image
from routes.integration_routes import router as integration_router
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
    title="MedApp Radiologues Service",
    description="API for managing radiologists profiles and related services",
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


# MongoDB collections
radiologues_collection = mongodb_client.db.radiologues
rapports_collection = mongodb_client.db.rapports
medtn_radiologues_collection = mongodb_client.db["medtn_radiologues"]


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
    response_model=Dict,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}},
)
async def signup(request: SignupRequest):
    if radiologues_collection.find_one({"email": request.email}):
        raise HTTPException(status_code=400, detail="Email already registered")

    radiologue = Radiologue(
        name=request.name,
        email=request.email,
        specialty=request.specialty,
        phone_number=request.phone_number,
        address=request.address,
        password=request.password,
    )

    # Insert the radiologue document with is_verified field
    result = radiologues_collection.insert_one(
        {
            "_id": radiologue._id,
            "name": radiologue.name,
            "email": radiologue.email,
            "password_hash": radiologue.password_hash,
            "specialty": radiologue.specialty,
            "phone_number": radiologue.phone_number,
            "address": radiologue.address,
            "is_verified": False,  # Add default verification status
        }
    )

    return radiologue.to_dict()


@app.post(
    "/api/login",
    response_model=LoginResponse,
    responses={401: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def login(request: LoginRequest):
    try:
        logger_service.debug(f"Login attempt for email: {request.email}")

        radiologue_data = radiologues_collection.find_one({"email": request.email})
        if not radiologue_data:
            logger_service.debug("Email not found")
            raise HTTPException(status_code=401, detail="Invalid credentials")

        radiologue = Radiologue.from_dict(radiologue_data)
        radiologue.password_hash = radiologue_data["password_hash"]

        if radiologue.check_password(request.password):
            token = create_access_token({"user_id": str(radiologue_data["_id"])})

            # Include verification status and details in response
            return LoginResponse(
                token=token,
                id=str(radiologue_data["_id"]),
                name=radiologue_data["name"],
                email=radiologue_data["email"],
                specialty=radiologue_data["specialty"],
                phone_number=radiologue_data.get("phone_number", ""),
                address=radiologue_data.get("address", ""),
                profile_image=radiologue_data.get("profile_image"),
                is_verified=radiologue_data.get("is_verified", False),
                verification_details=radiologue_data.get("verification_details", None),
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

        radiologue_data = radiologues_collection.find_one({"email": email})
        if not radiologue_data:
            logger_service.debug(f"Email not found: {email}")
            raise HTTPException(status_code=404, detail="Email not found")

        otp = str(random.randint(100000, 999999))
        logger_service.debug(f"Generated OTP: {otp}")

        if send_otp_email(email, otp):
            radiologues_collection.update_one(
                {"email": email},
                {
                    "$set": {
                        "reset_otp": otp,
                        "otp_expiry": datetime.utcnow() + timedelta(minutes=15),
                    }
                },
            )
            logger_service.debug("OTP sent and saved successfully")
            return MessageResponse(message="OTP sent successfully")
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
    result = radiologues_collection.find_one(
        {
            "email": request.email,
            "reset_otp": request.otp,
            "otp_expiry": {"$gt": datetime.utcnow()},
        }
    )

    if not result:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    return MessageResponse(message="OTP verified successfully")


@app.post(
    "/api/reset-password",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def reset_password(request: ResetPasswordRequest):
    radiologue_data = radiologues_collection.find_one(
        {
            "email": request.email,
            "reset_otp": request.otp,
            "otp_expiry": {"$gt": datetime.utcnow()},
        }
    )

    if not radiologue_data:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    # Create a Radiologue instance and set the new password
    radiologue = Radiologue.from_dict(radiologue_data)
    radiologue.set_password(request.new_password)

    # Update the password hash and remove the OTP data
    result = radiologues_collection.update_one(
        {"email": request.email},
        {
            "$set": {"password_hash": radiologue.password_hash},
            "$unset": {"reset_otp": "", "otp_expiry": ""},
        },
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Failed to update password")

    return MessageResponse(message="Password reset successful")


@app.get("/api/profile", response_model=Dict, responses={404: {"model": ErrorResponse}})
async def get_profile(user_info: Dict = Depends(get_current_user)):
    user_id = user_info.get("user_id")
    radiologue_data = radiologues_collection.find_one({"_id": ObjectId(user_id)})
    if not radiologue_data:
        raise HTTPException(status_code=404, detail="Radiologue not found")

    # Create a Radiologue instance
    radiologue = Radiologue.from_dict(radiologue_data)

    # Get response data
    response_data = radiologue.to_dict()

    # Include verification status
    response_data["is_verified"] = radiologue_data.get("is_verified", False)
    response_data["verification_details"] = radiologue_data.get("verification_details")

    return response_data


@app.get("/api/radiologues", response_model=List[Dict])
async def get_radiologues():
    try:
        radiologues = radiologues_collection.find()
        radiologues_list = [Radiologue.from_dict(doc).to_dict() for doc in radiologues]
        return radiologues_list
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la récupération des radiologues : {str(e)}",
        )


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
    current_password: str = Body(..., embed=True),
    new_password: str = Body(..., embed=True),
    user_info: Dict = Depends(get_current_user),
):
    user_id = user_info.get("user_id")
    radiologue_data = radiologues_collection.find_one({"_id": ObjectId(user_id)})
    if not radiologue_data:
        raise HTTPException(status_code=404, detail="Radiologue not found")

    radiologue = Radiologue.from_dict(radiologue_data)
    radiologue.password_hash = radiologue_data["password_hash"]

    if not radiologue.check_password(current_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    # Set and hash the new password
    radiologue.set_password(new_password)

    # Update the password hash in the database
    result = radiologues_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"password_hash": radiologue.password_hash}},
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Failed to update password")

    return MessageResponse(message="Password updated successfully")


@app.put(
    "/api/update-profile",
    response_model=Dict,
    responses={404: {"model": ErrorResponse}},
)
async def update_profile(
    name: Optional[str] = Body(None),
    specialty: Optional[str] = Body(None),
    phone_number: Optional[str] = Body(None),
    address: Optional[str] = Body(None),
    profile_image: Optional[str] = Body(None),
    user_info: Dict = Depends(get_current_user),
):
    user_id = user_info.get("user_id")

    # Get current radiologue data to preserve verification status
    current_radiologue = radiologues_collection.find_one({"_id": ObjectId(user_id)})
    if not current_radiologue:
        raise HTTPException(status_code=404, detail="Radiologue not found")

    # Prepare update fields, only include non-None values
    update_fields = {}
    if name is not None:
        update_fields["name"] = name
    if specialty is not None:
        update_fields["specialty"] = specialty
    if phone_number is not None:
        update_fields["phone_number"] = phone_number
    if address is not None:
        update_fields["address"] = address
    if profile_image is not None:
        update_fields["profile_image"] = profile_image

    # Update database
    radiologues_collection.update_one(
        {"_id": ObjectId(user_id)}, {"$set": update_fields}
    )

    # Get updated radiologue data
    updated_radiologue = radiologues_collection.find_one({"_id": ObjectId(user_id)})
    response_data = Radiologue.from_dict(updated_radiologue).to_dict()

    # Include verification status and details in response
    response_data["is_verified"] = current_radiologue.get("is_verified", False)
    response_data["verification_details"] = current_radiologue.get(
        "verification_details"
    )
    response_data["profile_image"] = updated_radiologue.get("profile_image")

    return response_data


@app.post("/api/logout", response_model=MessageResponse)
async def logout(user_info: Dict = Depends(get_current_user)):
    # Optionally blacklist or track tokens here if desired
    return MessageResponse(message="Logged out successfully")


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
    "/api/rapport",
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def ajouter_rapport(
    patient_name: str = Body(...),
    exam_type: str = Body(...),
    report_type: str = Body(...),
    content: str = Body(...),
):
    rapport = {
        "patientName": patient_name,
        "examType": exam_type,
        "reportType": report_type,
        "content": content,
        "date": datetime.utcnow(),
        "status": "pending_analysis",
    }

    try:
        # Insert report
        result = rapports_collection.insert_one(rapport)
        report_id = str(result.inserted_id)

        # Publish event for analysis
        rabbitmq_client.publish_radiology_report(
            report_id,
            {
                "patientName": patient_name,
                "examType": exam_type,
                "reportType": report_type,
                "content": content,
            },
        )

        return {"message": "Rapport ajouté avec succès", "rapport_id": report_id}
    except Exception as e:
        logger_service.error(f"Error creating report: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create report: {str(e)}"
        )


@app.get("/api/rapports", response_model=List[Dict])
async def afficher_rapports():
    """Récupère tous les rapports triés par date descendante."""
    try:
        rapports = rapports_collection.find().sort("date", -1)  # DESCENDING
        rapport_list = []

        for rapport in rapports:
            rapport_list.append(
                {
                    "_id": str(rapport["_id"]),
                    "patientName": rapport.get("patientName", "Inconnu"),
                    "examType": rapport.get("examType", "Non spécifié"),
                    "reportType": rapport.get("reportType", "Non spécifié"),
                    "content": rapport.get("content", "Aucun contenu"),
                    "date": str(rapport["date"]) if "date" in rapport else None,
                }
            )

        return rapport_list

    except Exception as e:
        logger_service.error(f"Erreur lors de la récupération des rapports: {e}")
        raise HTTPException(
            status_code=500, detail=f"Une erreur est survenue: {str(e)}"
        )


@app.post(
    "/api/verify-radiologue",
    response_model=VerifyRadiologueResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def verify_radiologue(
    request: VerifyRadiologueRequest, user_info: Dict = Depends(get_current_user)
):
    try:
        user_id = user_info.get("user_id")
        image_data = request.image

        if not image_data:
            raise HTTPException(status_code=400, detail="No image provided")

        # Get radiologue's data from database
        radiologue_data = radiologues_collection.find_one({"_id": ObjectId(user_id)})
        if not radiologue_data:
            raise HTTPException(status_code=404, detail="Radiologue not found")

        # Get radiologue's name from database
        radiologue_name = radiologue_data["name"].lower().strip()

        logger_service.debug(f"Checking for Name='{radiologue_name}'")

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
        name_found = radiologue_name in extracted_text

        # If name has multiple parts, check each part
        if not name_found:
            name_parts = radiologue_name.split()
            name_found = all(part in extracted_text for part in name_parts)

        logger_service.debug(f"Name found: {name_found}")

        if name_found:
            # Update verification status
            result = radiologues_collection.update_one(
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
                return VerifyRadiologueResponse(
                    verified=True, message="Name verification successful"
                )
            else:
                raise HTTPException(
                    status_code=500, detail="Failed to update verification status"
                )
        else:
            return VerifyRadiologueResponse(
                verified=False,
                error="Verification failed: name not found in document",
                debug_info={
                    "name_found": name_found,
                    "radiologue_name": radiologue_name,
                },
            )

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Verification error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")


@app.get("/api/generate-pdf")
async def generate_pdf():
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Rapport Médical", ln=True, align="C")
    pdf.cell(200, 10, txt="Patient: John Doe", ln=True, align="L")
    pdf.cell(200, 10, txt="Type d'examen: Radiographie", ln=True, align="L")
    pdf.cell(200, 10, txt="Date: 2023-10-01", ln=True, align="L")

    # Save PDF to a temporary file
    pdf_file = "rapport.pdf"
    pdf.output(pdf_file)

    # Return the file
    return FileResponse(
        path=pdf_file, filename="rapport.pdf", media_type="application/pdf"
    )


@app.get("/api/scrape_radiologues", response_model=MessageResponse)
async def scrape_and_store_radiologues():
    radiologues = scrape_medtn_radiologues()
    if radiologues:
        medtn_radiologues_collection.insert_many(radiologues)
        return MessageResponse(message="Données des médecins insérées avec succès.")
    else:
        raise HTTPException(status_code=400, detail="Aucune donnée à insérer.")


@app.get("/api/radiologues_med", response_model=List[Dict])
async def get_radiologues_med():
    radiologues = list(medtn_radiologues_collection.find({}, {"_id": 0}))
    return radiologues


# Extraction helper functions
def extract_name(text):
    # Look for patterns that might indicate a name
    # Usually names appear at the beginning or after "Dr." or similar titles
    lines = text.split("\n")
    for line in lines:
        # Look for "Dr." or similar titles
        name_match = re.search(
            r"(?:Dr\.?|Radiologue)\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
            line,
            re.IGNORECASE,
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


def scrape_medtn_radiologues():
    """Scrapes radiologists data from med.tn"""
    base_url = "https://www.med.tn/medecin"
    response = requests.get(base_url)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        radiologues = []
        for radiologue_card in soup.find_all("div", class_="radiologue-card"):
            name = radiologue_card.find("h2").text.strip()
            specialty = radiologue_card.find("p", class_="specialty").text.strip()
            location = radiologue_card.find("p", class_="location").text.strip()
            profile_url = radiologue_card.find("a", class_="profile-link")["href"]
            radiologue = {
                "name": name,
                "specialty": specialty,
                "location": location,
                "profile_url": profile_url,
            }
            radiologues.append(radiologue)
        return radiologues
    else:
        logger_service.error(f"Failed to retrieve data: {response.status_code}")
        return []


@app.get(
    "/api/reports",
    response_model=RadiologyReportsListResponse,
    responses={500: {"model": ErrorResponse}},
)
async def get_radiology_reports(
    doctor_id: Optional[str] = None,
    patient_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
):
    """Get radiology reports with filtering options"""
    try:
        # Build query based on parameters
        query = {}
        if doctor_id:
            query["doctor_id"] = doctor_id
        if patient_id:
            query["patient_id"] = patient_id
        if status:
            query["status"] = status

        # Get total count for pagination
        total = rapports_collection.count_documents(query)

        # Calculate skip based on page and limit
        skip = (page - 1) * limit

        # Get paginated results
        cursor = (
            rapports_collection.find(query).sort("date", -1).skip(skip).limit(limit)
        )

        # Convert to list of reports
        reports = []
        for report in cursor:
            report["id"] = str(report.pop("_id"))
            # Format dates for serialization
            if "date" in report:
                report["created_at"] = report["date"].isoformat()
                report.pop("date")
            if "updated_at" in report and isinstance(report["updated_at"], datetime):
                report["updated_at"] = report["updated_at"].isoformat()

            reports.append(report)

        return {
            "items": reports,
            "total": total,
            "page": page,
            "pages": (total + limit - 1) // limit if limit > 0 else 1,
        }

    except Exception as e:
        logger_service.error(f"Error retrieving radiology reports: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve radiology reports: {str(e)}"
        )


@app.get(
    "/api/reports/{report_id}",
    response_model=RadiologyReportResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_radiology_report(report_id: str):
    """Get a specific radiology report by ID"""
    try:
        # Validate ID format
        if not ObjectId.is_valid(report_id):
            raise HTTPException(status_code=400, detail="Invalid report ID format")

        # Find report
        report = rapports_collection.find_one({"_id": ObjectId(report_id)})

        if not report:
            raise HTTPException(status_code=404, detail="Report not found")

        # Format report for serialization
        report["id"] = str(report.pop("_id"))

        # Format dates for serialization
        if "date" in report:
            report["created_at"] = report["date"].isoformat()
            report.pop("date")
        if "updated_at" in report and isinstance(report["updated_at"], datetime):
            report["updated_at"] = report["updated_at"].isoformat()

        return report

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error retrieving radiology report: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve radiology report: {str(e)}"
        )


@app.post(
    "/api/reports",
    response_model=RadiologyReportResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def create_radiology_report(
    request: RadiologyReportRequest,
    user_info: Dict = Depends(get_current_user),
):
    """Create a new radiology report"""
    try:
        radiologue_id = user_info.get("user_id")

        # Get radiologist info
        radiologue = radiologues_collection.find_one({"_id": ObjectId(radiologue_id)})
        if not radiologue:
            raise HTTPException(status_code=404, detail="Radiologist not found")

        # Create report
        new_report = {
            "patient_id": request.patient_id,
            "patient_name": request.patient_name,
            "doctor_id": request.doctor_id,
            "doctor_name": request.doctor_name,
            "radiologist_id": radiologue_id,
            "radiologist_name": radiologue.get("name", "Unknown Radiologist"),
            "exam_type": request.exam_type,
            "report_type": request.report_type,
            "content": request.content,
            "findings": request.findings,
            "conclusion": request.conclusion,
            "status": "completed",
            "date": datetime.utcnow(),
            "images": request.images or [],
        }

        # Insert into database
        result = rapports_collection.insert_one(new_report)

        # Get the created report
        created_report = rapports_collection.find_one({"_id": result.inserted_id})

        # Format for response
        created_report["id"] = str(created_report.pop("_id"))
        created_report["created_at"] = created_report["date"].isoformat()
        created_report.pop("date")

        # Notify doctor about new report via RabbitMQ
        if request.doctor_id:
            rabbitmq_client.publish_message(
                exchange="medical.reports",
                routing_key="report.completed",
                message={
                    "report_id": created_report["id"],
                    "doctor_id": request.doctor_id,
                    "patient_id": request.patient_id,
                    "exam_type": request.exam_type,
                    "status": "completed",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

        return created_report

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error creating radiology report: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create radiology report: {str(e)}"
        )


# Include the integration router
app.include_router(integration_router)

# Import the consumer module and threading
import threading
from consumer import main as consumer_main

if __name__ == "__main__":
    # Start the consumer in a separate thread
    consumer_thread = threading.Thread(target=consumer_main, daemon=True)
    consumer_thread.start()
    
    # Run the FastAPI app with uvicorn in the main thread
    uvicorn.run(
        "app:app", host=Config.HOST, port=Config.PORT, reload=True, log_level="debug"
    )
