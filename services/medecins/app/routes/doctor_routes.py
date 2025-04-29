from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import Dict, List, Optional
from datetime import datetime
import base64
import io
import re

from bson import ObjectId
from PIL import Image
import pytesseract

from auth.keycloak_auth import get_current_user
from models.api_models import (
    ErrorResponse, ScanVisitCardRequest, ScanVisitCardResponse,
    VerifyDoctorRequest, VerifyDoctorResponse, UpdateSignatureRequest
)
from services.logger_service import logger_service
from config import Config
from services.mongodb_client import MongoDBClient

mongodb_client = MongoDBClient(Config)

router = APIRouter()

@router.post(
    "/api/scan-visit-card",
    response_model=ScanVisitCardResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def scan_visit_card(request: ScanVisitCardRequest):
    if not request.image:
        raise HTTPException(status_code=400, detail="No image provided")

    try:
        image = Image.open(io.BytesIO(base64.b64decode(request.image)))
        text = pytesseract.image_to_string(image)
        name = extract_name(text)
        email = extract_email(text)
        specialty = extract_specialty(text)
        phone = extract_phone(text)
        return ScanVisitCardResponse(
            name=name,
            email=email,
            specialty=specialty,
            phone=phone,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
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

        doctor_data = mongodb_client.db.doctors.find_one({"_id": ObjectId(user_id)})
        if not doctor_data:
            raise HTTPException(status_code=404, detail="Doctor not found")

        doctor_name = doctor_data["name"].lower().strip()
        logger_service.debug(f"Checking for Name='{doctor_name}'")

        image = Image.open(io.BytesIO(base64.b64decode(image_data)))
        image = image.convert("L")
        image = image.point(lambda x: 0 if x < 128 else 255, "1")
        extracted_text = pytesseract.image_to_string(image)
        extracted_text = extracted_text.lower().strip()
        logger_service.debug(f"Extracted text: {extracted_text}")

        name_found = doctor_name in extracted_text
        if not name_found:
            name_parts = doctor_name.split()
            name_found = all(part in extracted_text for part in name_parts)
        logger_service.debug(f"Name found: {name_found}")

        if name_found:
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


@router.post(
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


@router.get(
    "/api/doctors",
    response_model=List[Dict],
    responses={500: {"model": ErrorResponse}},
)
async def get_all_doctors(
    skip: int = Query(2000, description="Number of doctors to skip"),
    limit: int = Query(2050, description="Maximum number of doctors to return"),
    # user_info: Dict = Depends(get_current_user)
):
    try:
        # Get doctors with pagination
        doctors_cursor = mongodb_client.db.doctors.find().skip(skip).limit(limit)
        
        # Convert to list and process ObjectId
        doctors = []
        for doc in doctors_cursor:
            doc["id"] = str(doc.pop("_id"))
            # Remove sensitive fields if needed
            if "password_hash" in doc:
                del doc["password_hash"]
            if "signature" in doc:
                # Indicate signature exists but don't return the actual data
                doc["has_signature"] = bool(doc["signature"])
                del doc["signature"]
            doctors.append(doc)
            
        return doctors
        
    except Exception as e:
        logger_service.error(f"Error retrieving doctors: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve doctors: {str(e)}")


# Extraction helper functions
def extract_name(text):
    lines = text.split("\n")
    for line in lines:
        name_match = re.search(
            r"(?:Dr\.?|Doctor)\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", line, re.IGNORECASE
        )
        if name_match:
            return name_match.group(1)
        name_match = re.search(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", line)
        if name_match:
            return name_match.group(1)
    return ""


def extract_email(text):
    email_match = re.search(r"[\w\.-]+@[\w\.-]+", text)
    if email_match:
        return email_match.group(0)
    return "Extracted Email"


def extract_specialty(text):
    specialties = [
        "Cardiology", "Dermatology", "Neurology", "Pediatrics", "Oncology",
        "Orthopedics", "Gynecology", "Psychiatry", "Surgery", "Internal Medicine",
    ]
    lines = text.split("\n")
    for line in lines:
        for specialty in specialties:
            if specialty.lower() in line.lower():
                return line.strip()
        specialty_match = re.search(
            r"(?:Specialist|Consultant)\s+in\s+([A-Za-z\s]+)", line
        )
        if specialty_match:
            return specialty_match.group(1).strip()
    return ""


def extract_phone(text):
    phone_match = re.search(r"(\+?\d[\d\s\-]{7,}\d)", text)
    if phone_match:
        return phone_match.group(0).strip()
    return "Extracted Phone"
