import base64
import io
import re
from datetime import datetime
from typing import Dict, List, Optional

import httpx
import requests
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fpdf import FPDF

# Create HTTPBearer instance
security = HTTPBearer()

from models.api_models import (
    ErrorResponse,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    RadiologyReportRequest,
    RadiologyReportResponse,
    RadiologyReportsListResponse,
    ResetPasswordRequest,
    ScanVisitCardRequest,
    ScanVisitCardResponse,
    SignupRequest,
    VerifyOTPRequest,
    VerifyRadiologueRequest,
    VerifyRadiologueResponse,
)
from models.radiologue import (
    PasswordChange,
    Radiologue,
    RadiologueCreate,
    RadiologueInDB,
    RadiologueUpdate,
)
from routes.integration_routes import router as integration_router
from services.logger_service import logger_service
from services.rabbitmq_client import RabbitMQClient
from services.redis_client import RedisClient
from services.tracing_service import TracingService
from PIL import Image
import pytesseract
from bs4 import BeautifulSoup
from config import Config

http_client = httpx.AsyncClient(timeout=30.0)
router = APIRouter(prefix="/api/radiologues", tags=["Radiologues"])
rabbitmq_client = RabbitMQClient(Config)


# Authentication service client functions
async def get_current_radiologist(
        credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict:
    """
    Get current radiologist information from auth service

    Returns:
        Dict: The user information with user_id and roles

    Raises:
        HTTPException: If the token is invalid or user is not a radiologist
    """
    try:
        token = credentials.credentials

        # Call auth service directly to verify token and get user info
        auth_url = f"{Config.AUTH_SERVICE_URL}/api/auth/token/verify"
        payload = {"token": token}

        async with http_client as client:
            response = await client.post(auth_url, json=payload)

            if response.status_code != 200:
                logger_service.error(
                    f"Failed to verify token: {response.status_code} - {response.text}"
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication token",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Get user info from response
            user_info = response.json()

            # Check if the user has the radiologist role
            roles = user_info.get("roles", [])
            if "radiologist" not in roles and "admin" not in roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Radiologist role required",
                )

            # Add token to user info for convenience
            user_info["token"] = token

            return user_info

    except httpx.RequestError as e:
        logger_service.error(f"Error connecting to auth service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Unexpected error during authentication: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication error",
        )


async def get_user_info(user_id: str, token: str = None) -> Dict:
    """
    Get user information from auth service

    Args:
        user_id: User ID
        token: Authentication token (optional)

    Returns:
        Dict: User information
    """
    try:
        auth_url = f"{Config.AUTH_SERVICE_URL}/api/auth/user/{user_id}"
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with http_client as client:
            response = await client.get(auth_url, headers=headers)

            if response.status_code != 200:
                logger_service.error(
                    f"Failed to get user info: {response.status_code} - {response.text}"
                )
                if response.status_code == 404:
                    return None
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Failed to get user information",
                )

            return response.json()
    except httpx.RequestError as e:
        logger_service.error(f"Error connecting to auth service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error getting user info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user information: {str(e)}",
        )


async def get_user_info(user_id: str, token: str = None) -> Dict:
    """
    Get user information from auth service

    Args:
        user_id: User ID
        token: Authentication token (optional)

    Returns:
        Dict: User information
    """
    try:
        auth_url = f"{Config.AUTH_SERVICE_URL}/api/auth/user/{user_id}"
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with http_client as client:
            response = await client.get(auth_url, headers=headers)

            if response.status_code != 200:
                logger_service.error(
                    f"Failed to get user info: {response.status_code} - {response.text}"
                )
                if response.status_code == 404:
                    return None
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Failed to get user information",
                )

            return response.json()
    except httpx.RequestError as e:
        logger_service.error(f"Error connecting to auth service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error getting user info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user information: {str(e)}",
        )


async def update_user_attributes(user_id: str, attributes: Dict, token: str) -> bool:
    """
    Update user attributes in auth service

    Args:
        user_id: User ID
        attributes: Attributes to update
        token: Authentication token

    Returns:
        bool: Success status
    """
    try:
        auth_url = f"{Config.AUTH_SERVICE_URL}/api/auth/users/{user_id}/attributes"
        headers = {"Authorization": f"Bearer {token}"}

        async with http_client as client:
            response = await client.patch(auth_url, json=attributes, headers=headers)

            if response.status_code != 200:
                logger_service.error(
                    f"Failed to update attributes: {response.status_code} - {response.text}"
                )
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Failed to update user attributes",
                )

            return True
    except httpx.RequestError as e:
        logger_service.error(f"Error connecting to auth service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error updating attributes: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update attributes: {str(e)}",
        )


async def request_password_reset(email: str) -> bool:
    """
    Request password reset via auth service

    Args:
        email: User's email

    Returns:
        bool: Success status
    """
    try:
        auth_url = f"{Config.AUTH_SERVICE_URL}/api/auth/forgot-password"
        payload = {"email": email}

        async with http_client as client:
            response = await client.post(auth_url, json=payload)

            # Even if the email doesn't exist, we return success for security reasons
            return True
    except Exception as e:
        logger_service.error(f"Error requesting password reset: {str(e)}")
        # Still return success for security reasons
        return True


async def verify_otp(user_id: str, otp: str) -> bool:
    """
    Verify OTP for password reset

    Args:
        user_id: User ID
        otp: One-time password

    Returns:
        bool: Verification status
    """
    try:
        auth_url = f"{Config.AUTH_SERVICE_URL}/api/auth/verify-otp"
        payload = {"user_id": user_id, "otp": otp}

        async with http_client as client:
            response = await client.post(auth_url, json=payload)

            if response.status_code != 200:
                logger_service.error(
                    f"OTP verification failed: {response.status_code} - {response.text}"
                )
                return False

            return True
    except Exception as e:
        logger_service.error(f"Error verifying OTP: {str(e)}")
        return False


async def reset_password(reset_token: str, new_password: str) -> bool:
    """
    Reset password using token

    Args:
        reset_token: Password reset token
        new_password: New password

    Returns:
        bool: Success status
    """
    try:
        auth_url = f"{Config.AUTH_SERVICE_URL}/api/auth/reset-password"
        payload = {"reset_token": reset_token, "new_password": new_password}

        async with http_client as client:
            response = await client.post(auth_url, json=payload)

            if response.status_code != 200:
                logger_service.error(
                    f"Password reset failed: {response.status_code} - {response.text}"
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Password reset failed",
                )

            return True
    except httpx.RequestError as e:
        logger_service.error(f"Error connecting to auth service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Password reset error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Password reset failed: {str(e)}",
        )


async def search_radiologists(
        name: str, skip: int, limit: int, token: str
) -> List[Dict]:
    """
    Search for radiologists by name

    Args:
        name: Name to search for
        skip: Number of records to skip
        limit: Maximum number of records to return
        token: Authentication token

    Returns:
        List[Dict]: List of radiologist data
    """
    try:
        auth_url = f"{Config.AUTH_SERVICE_URL}/api/auth/users"
        headers = {"Authorization": f"Bearer {token}"}
        params = {"role": "radiologist", "name": name, "first": skip, "max": limit}

        async with http_client as client:
            response = await client.get(auth_url, headers=headers, params=params)

            if response.status_code != 200:
                logger_service.error(
                    f"Failed to search radiologists: {response.status_code} - {response.text}"
                )
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Failed to search radiologists",
                )

            return response.json()
    except httpx.RequestError as e:
        logger_service.error(f"Error connecting to auth service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error searching radiologists: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search radiologists: {str(e)}",
        )


async def get_all_radiologists(skip: int, limit: int, token: str) -> List[Dict]:
    """
    Get all radiologists

    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        token: Authentication token

    Returns:
        List[Dict]: List of radiologist data
    """
    try:
        auth_url = f"{Config.AUTH_SERVICE_URL}/api/auth/users"
        headers = {"Authorization": f"Bearer {token}"}
        params = {"role": "radiologist", "first": skip, "max": limit}

        async with http_client as client:
            response = await client.get(auth_url, headers=headers, params=params)

            if response.status_code != 200:
                logger_service.error(
                    f"Failed to get radiologists: {response.status_code} - {response.text}"
                )
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Failed to get radiologists",
                )

            return response.json()
    except httpx.RequestError as e:
        logger_service.error(f"Error connecting to auth service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error getting radiologists: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get radiologists: {str(e)}",
        )


# Reports service client functions
async def get_radiology_reports_from_service(
        doctor_id: Optional[str] = None,
        patient_id: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        limit: int = 10,
        token: Optional[str] = None,
) -> Dict:
    """
    Get radiology reports from the reports service

    Args:
        doctor_id: Filter by doctor ID
        patient_id: Filter by patient ID
        status: Filter by status
        page: Page number
        limit: Number of items per page
        token: Auth token

    Returns:
        Dict with reports list and pagination info
    """
    try:
        reports_url = f"{Config.REPORTS_SERVICE_URL}/api/integration/reports"

        # Build query params
        params = {"page": page, "limit": limit}
        if doctor_id:
            params["doctor_id"] = doctor_id
        if patient_id:
            params["patient_id"] = patient_id
        if status:
            params["status"] = status

        # Set headers if token is provided
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        # Get reports from reports service
        async with http_client as client:
            response = await client.get(reports_url, params=params, headers=headers)

            if response.status_code != 200:
                logger_service.error(
                    f"Failed to get reports: {response.status_code} - {response.text}"
                )
                # Return empty results on error
                return {"items": [], "total": 0, "page": page, "pages": 0}

            return response.json()

    except httpx.RequestError as e:
        logger_service.error(f"Error connecting to reports service: {str(e)}")
        return {"items": [], "total": 0, "page": page, "pages": 0}
    except Exception as e:
        logger_service.error(f"Error getting reports: {str(e)}")
        return {"items": [], "total": 0, "page": page, "pages": 0}


async def get_radiology_report_from_service(
        report_id: str, token: Optional[str] = None
) -> Optional[Dict]:
    """
    Get a specific radiology report from the reports service

    Args:
        report_id: ID of the report to retrieve
        token: Auth token

    Returns:
        Report data or None if not found
    """
    try:
        reports_url = (
            f"{Config.REPORTS_SERVICE_URL}/api/integration/reports/{report_id}"
        )

        # Set headers if token is provided
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        # Get report from reports service
        async with http_client as client:
            response = await client.get(reports_url, headers=headers)

            if response.status_code == 404:
                return None

            if response.status_code != 200:
                logger_service.error(
                    f"Failed to get report: {response.status_code} - {response.text}"
                )
                return None

            return response.json()

    except httpx.RequestError as e:
        logger_service.error(f"Error connecting to reports service: {str(e)}")
        return None
    except Exception as e:
        logger_service.error(f"Error getting report: {str(e)}")
        return None


async def create_radiology_report_in_service(
        report_data: Dict, radiologue_id: str, radiologue_name: str, token: str
) -> Optional[Dict]:
    """
    Create a new radiology report in the reports service

    Args:
        report_data: Report data
        radiologue_id: ID of the radiologist creating the report
        radiologue_name: Name of the radiologist
        token: Auth token

    Returns:
        Created report data or None if creation failed
    """
    try:
        reports_url = f"{Config.REPORTS_SERVICE_URL}/api/integration/reports"

        # Add radiologist info to report data
        report_data["radiologist_id"] = radiologue_id
        report_data["radiologist_name"] = radiologue_name

        # Set headers with token
        headers = {"Authorization": f"Bearer {token}"}

        # Create report in reports service
        async with http_client as client:
            response = await client.post(reports_url, json=report_data, headers=headers)

            if response.status_code != 201:
                logger_service.error(
                    f"Failed to create report: {response.status_code} - {response.text}"
                )
                return None

            return response.json()

    except httpx.RequestError as e:
        logger_service.error(f"Error connecting to reports service: {str(e)}")
        return None
    except Exception as e:
        logger_service.error(f"Error creating report: {str(e)}")
        return None


@router.get(
    "/api/radiologues",
    response_model=List[RadiologueInDB],
    responses={401: {"model": ErrorResponse}},
)
async def get_radiologues(
        skip: int = 0,
        limit: int = 10,
        name: Optional[str] = None,
        specialty: Optional[str] = None,
        credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """List radiologists, optionally filtered by name or specialty"""
    try:
        # Get token from credentials
        token = credentials.credentials

        if name:
            # Search for radiologists by name
            radiologues_data = await search_radiologists(name, skip, limit, token)
        else:
            # Get all radiologists
            radiologues_data = await get_all_radiologists(skip, limit, token)

        # Filter by specialty if provided
        if specialty and radiologues_data:
            filtered_radiologues = []
            for r in radiologues_data:
                specialty_attr = r.get("attributes", {}).get("specialty", [])
                if isinstance(specialty_attr, list) and specialty_attr:
                    if specialty.lower() in specialty_attr[0].lower():
                        filtered_radiologues.append(r)
                else:
                    specialty_str = r.get("attributes", {}).get("specialty", "")
                    if specialty.lower() in specialty_str.lower():
                        filtered_radiologues.append(r)
            radiologues_data = filtered_radiologues

        # Convert to Radiologue instances
        result = []
        for data in radiologues_data:
            radiologue = Radiologue.from_keycloak_data(data)
            result.append(radiologue.to_pydantic())

        return result
    except Exception as e:
        logger_service.error(f"Error retrieving radiologists: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve radiologists: {str(e)}"
        )


@router.get(
    "/api/radiologues/{radiologue_id}",
    response_model=RadiologueInDB,
    responses={404: {"model": ErrorResponse}},
)
async def get_radiologue_by_id(
        radiologue_id: str,
        credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Get a radiologist by ID"""
    try:
        # Get radiologist data from Keycloak
        token = credentials.credentials
        radiologue_data = await get_user_info(radiologue_id, token)

        if not radiologue_data:
            raise HTTPException(status_code=404, detail="Radiologist not found")

        # Check if the user has the radiologist role
        roles = radiologue_data.get("roles", [])
        if "radiologist" not in roles:
            raise HTTPException(status_code=404, detail="Radiologist not found")

        # Create a Radiologue instance
        radiologue = Radiologue.from_keycloak_data(radiologue_data)
        return radiologue.to_pydantic()
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error retrieving radiologist: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve radiologist: {str(e)}"
        )


@router.post(
    "/api/verify-radiologue",
    response_model=VerifyRadiologueResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def verify_radiologue(
        request: VerifyRadiologueRequest, user_info: Dict = Depends(get_current_radiologist)
):
    """Verify a radiologist's identity using document image"""
    try:
        user_id = user_info.get("user_id")
        image_data = request.image
        token = user_info.get("token")

        if not image_data:
            raise HTTPException(status_code=400, detail="No image provided")

        # Get radiologist's data from Keycloak
        radiologue_data = await get_user_info(user_id, token)
        if not radiologue_data:
            raise HTTPException(status_code=404, detail="Radiologist not found")

        # Get radiologist's name
        radiologue_name = radiologue_data.get("name", "").lower().strip()

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
            # Update verification status in Keycloak
            verification_details = {
                "verified_at": datetime.utcnow().isoformat(),
                "matched_text": extracted_text,
            }

            attributes = {
                "is_verified": "true",
                "verification_details": str(verification_details),
            }

            await update_user_attributes(user_id, attributes, token)

            return VerifyRadiologueResponse(
                verified=True, message="Name verification successful"
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


@router.post(
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
    "/api/rapport",
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def ajouter_rapport(
        patient_name: str = Body(...),
        exam_type: str = Body(...),
        report_type: str = Body(...),
        content: str = Body(...),
        credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Create a new radiology report with basic information"""
    try:
        # Get token and user info
        token = credentials.credentials
        user_info = await get_current_radiologist(credentials)
        radiologue_id = user_info.get("user_id")

        # Get radiologist name
        radiologue_data = await get_user_info(radiologue_id, token)
        if not radiologue_data:
            raise HTTPException(status_code=404, detail="Radiologist not found")

        radiologue_name = radiologue_data.get("name", "Unknown Radiologist")

        # Prepare report data
        report_data = {
            "patient_name": patient_name,
            "exam_type": exam_type,
            "report_type": report_type,
            "content": content,
            "status": "pending_analysis",
        }

        # Create report using reports service
        new_report = await create_radiology_report_in_service(
            report_data, radiologue_id, radiologue_name, token
        )

        if not new_report:
            raise HTTPException(status_code=500, detail="Failed to create report")

        # Publish event for analysis if needed
        if "id" in new_report:
            rabbitmq_client.publish_radiology_report(
                new_report["id"],
                {
                    "patientName": patient_name,
                    "examType": exam_type,
                    "reportType": report_type,
                    "content": content,
                },
            )

        return {
            "message": "Rapport ajouté avec succès",
            "rapport_id": new_report.get("id"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error creating report: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create report: {str(e)}"
        )


@router.get("/api/rapports", response_model=List[Dict])
async def afficher_rapports(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        page: int = Query(1, ge=1),
        limit: int = Query(50, ge=1, le=100),
):
    """Récupère tous les rapports triés par date descendante en utilisant le service de rapports."""
    try:
        # Get token from credentials
        token = credentials.credentials

        # Use reports service communication method
        reports_data = await get_radiology_reports_from_service(
            page=page,
            limit=limit,
            token=token,
        )

        # Format results for compatibility with existing frontend
        rapport_list = []

        for report in reports_data.get("items", []):
            rapport_list.append(
                {
                    "_id": report.get("id"),
                    "patientName": report.get("patient_name", "Inconnu"),
                    "examType": report.get("exam_type", "Non spécifié"),
                    "reportType": report.get("report_type", "Non spécifié"),
                    "content": report.get("content", "Aucun contenu"),
                    "date": report.get("created_at"),
                }
            )

        return rapport_list

    except Exception as e:
        logger_service.error(f"Erreur lors de la récupération des rapports: {e}")
        raise HTTPException(
            status_code=500, detail=f"Une erreur est survenue: {str(e)}"
        )


@router.get("/api/generate-pdf")
async def generate_pdf():
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


@router.get(
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
        credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Get radiology reports with filtering options"""
    try:
        # Get token from credentials
        token = credentials.credentials

        # Use reports service communication method
        reports = await get_radiology_reports_from_service(
            doctor_id=doctor_id,
            patient_id=patient_id,
            status=status,
            page=page,
            limit=limit,
            token=token,
        )

        return reports

    except Exception as e:
        logger_service.error(f"Error retrieving radiology reports: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve radiology reports: {str(e)}"
        )


@router.get(
    "/api/reports/{report_id}",
    response_model=RadiologyReportResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_radiology_report(
        report_id: str,
        credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Get a specific radiology report by ID"""
    try:
        # Get token from credentials
        token = credentials.credentials

        # Use reports service to get the report
        report = await get_radiology_report_from_service(report_id, token)

        if not report:
            raise HTTPException(status_code=404, detail="Report not found")

        return report

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error retrieving radiology report: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve radiology report: {str(e)}"
        )


@router.post(
    "/api/reports",
    response_model=RadiologyReportResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def create_radiology_report(
        request: RadiologyReportRequest,
        user_info: Dict = Depends(get_current_radiologist),
):
    """Create a new radiology report"""
    try:
        radiologue_id = user_info.get("user_id")
        token = user_info.get("token")

        # Get radiologist info from Keycloak
        radiologue_data = await get_user_info(radiologue_id, token)
        if not radiologue_data:
            raise HTTPException(status_code=404, detail="Radiologist not found")

        # Create report data
        report_data = {
            "patient_id": request.patient_id,
            "patient_name": request.patient_name,
            "doctor_id": request.doctor_id,
            "doctor_name": request.doctor_name,
            "exam_type": request.exam_type,
            "report_type": request.report_type,
            "content": request.content,
            "findings": request.findings,
            "conclusion": request.conclusion,
            "status": "completed",
            "images": request.images or [],
        }

        # Create report using reports service
        radiologue_name = radiologue_data.get("name", "Unknown Radiologist")
        created_report = await create_radiology_report_in_service(
            report_data, radiologue_id, radiologue_name, token
        )

        if not created_report:
            raise HTTPException(status_code=500, detail="Failed to create report")

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
    return ""


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
        "Radiology",
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


def extract_phone(text):
    # Basic pattern to match phone formats, can be refined
    phone_match = re.search(r"(\+?\d[\d\s\-]{7,}\d)", text)
    if phone_match:
        return phone_match.group(0).strip()
    return ""


def scrape_medtn_radiologues():
    """Scrapes radiologists data from med.tn"""
    try:
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
    except Exception as e:
        logger_service.error(f"Error scraping radiologues data: {e}")
        return []
