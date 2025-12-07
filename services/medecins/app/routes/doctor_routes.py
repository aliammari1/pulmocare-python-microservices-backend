import base64
import io
import re
from typing import Dict, Optional

import httpx
import pytesseract
from PIL import Image
from fastapi import (
    APIRouter,
    HTTPException,
    Depends,
    status,
    Query,
    File,
    UploadFile,
    Response,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from models.api_models import (
    ErrorResponse,
    ScanVisitCardRequest,
    ScanVisitCardResponse,
    VerifyDoctorRequest,
    VerifyDoctorResponse,
    UpdateSignatureRequest,
    DoctorVerificationInfoResponse,
    MessageResponse,
    UpdateProfileResponse,
    DoctorListResponse,
    DoctorListItem,
)
from models.doctor import Doctor, DoctorUpdate
from services.logger_service import logger_service

from config import Config

config = Config()
router = APIRouter(prefix="/api/doctors", tags=["Doctors"])
security = HTTPBearer()


# Don't create a global HTTP client - create a new one when needed


async def get_authenticated_user_from_auth_service(token: str) -> Dict:
    """
    Get current user information directly from auth service without role requirement

    Args:
        token: The access token from the request

    Returns:
        Dict: The user information with user_id and roles

    Raises:
        HTTPException: If the token is invalid
    """
    try:
        # Call auth service directly to verify token and get user info
        auth_url = f"{config.AUTH_SERVICE_URL}/api/auth/token/verify"
        headers = {"Authorization": f"Bearer {token}"}
        # Include the token in the request body as required by the auth service
        body = {"token": token}

        # Create a new client for each request
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(auth_url, headers=headers, json=body)

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


async def get_doctor_from_auth_service(token: str) -> Dict:
    """
    Get current doctor information directly from auth service

    Args:
        token: The access token from the request

    Returns:
        Dict: The doctor information with user_id and roles

    Raises:
        HTTPException: If the token is invalid or user is not a doctor
    """
    # First, get authenticated user without role check
    user_info = await get_authenticated_user_from_auth_service(token)

    # Then check if the user has the doctor role
    roles = user_info.get("roles", [])
    if "doctor" not in roles and "admin" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Doctor role required",
        )

    return user_info


async def get_authenticated_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict:
    """
    Get current user information from auth service without role requirement

    Returns:
        Dict: The user information with user_id and roles

    Raises:
        HTTPException: If the token is invalid
    """
    token = credentials.credentials
    return await get_authenticated_user_from_auth_service(token)


async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict:
    """
    Get current user information from auth service with doctor role requirement

    Returns:
        Dict: The doctor information with user_id and roles

    Raises:
        HTTPException: If the token is invalid or user is not a doctor
    """
    token = credentials.credentials
    return await get_doctor_from_auth_service(token)


def is_healthcare_provider(roles):
    return any(role in roles for role in ["doctor", "radiologist", "admin"])


async def get_doctor_by_id(doctor_id: str, token: str, user_info: Dict = None) -> Dict:
    """
    Get doctor information by ID from auth service
    Allow any authenticated user to access doctor information
    """
    try:
        # We removed the access control check to allow patients to view doctor info
        # This enables patient users to view doctor profiles and listings
        # Call auth service directly to get user info
        auth_url = f"{config.AUTH_SERVICE_URL}/api/auth/users/{doctor_id}"
        headers = {"Authorization": f"Bearer {token}"}

        # Create a new client for each request
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(auth_url, headers=headers)

            if response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Doctor not found",
                )

            if response.status_code != 200:
                logger_service.error(
                    f"Failed to get user info: {response.status_code} - {response.text}"
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to retrieve user information",
                )

            # Get user info from response
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
        logger_service.error(f"Unexpected error retrieving user info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving user information",
        )


@router.post(
    "/scan-visit-card",
    response_model=ScanVisitCardResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def scan_visit_card(
        file: UploadFile = File(...),
        credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Scan a business card to extract doctor information"""
    try:
        # Get the token from the request
        token = credentials.credentials

        # Get doctor info from auth service
        user_info = await get_doctor_from_auth_service(token)

        # Check file format
        if file.content_type not in ["image/jpeg", "image/png", "image/jpg"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid file format. Please upload a JPEG or PNG image.",
            )

        # Read file content
        contents = await file.read()
        if len(contents) > 5 * 1024 * 1024:  # 5MB limit
            raise HTTPException(
                status_code=400, detail="File size too large. Maximum size is 5MB."
            )

        # Use PyTesseract to extract text from image
        image = Image.open(io.BytesIO(contents))
        extracted_text = pytesseract.image_to_string(image)

        # Simple parsing of the extracted text (this is a basic implementation)
        lines = extracted_text.strip().split("\n")
        doctor_info = {}

        # Try to extract information
        if len(lines) > 0:
            doctor_info["name"] = lines[0].strip()  # Assuming first line is the name

        # Look for email
        for line in lines:
            if "@" in line and "." in line:
                doctor_info["email"] = line.strip()
                break

        # Look for phone number (simple regex pattern)
        phone_pattern = re.compile(r"\+?[\d\s\(\)-]{10,}")
        for line in lines:
            match = phone_pattern.search(line)
            if match:
                doctor_info["phone"] = match.group().strip()
                break

        # Look for address (assuming it's multiple lines with postal code)
        address_lines = []
        for line in lines:
            if re.search(r"\d{5}", line):  # Check for postal code
                address_lines.append(line.strip())

        if address_lines:
            doctor_info["address"] = " ".join(address_lines)

        # Look for specialty
        specialties = [
            "Cardiology",
            "Neurology",
            "Dermatology",
            "Pediatrics",
            "Oncology",
        ]
        for line in lines:
            for specialty in specialties:
                if specialty.lower() in line.lower():
                    doctor_info["specialty"] = specialty
                    break

        return {
            "extracted_info": doctor_info,
            "raw_text": extracted_text,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error scanning business card: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error scanning business card: {str(e)}"
        )


@router.post(
    "/verify",
    response_model=VerifyDoctorResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def verify_doctor(
        request: VerifyDoctorRequest,
        credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Submit verification documentation for a doctor"""
    try:
        # Get token from request
        token = credentials.credentials

        # Get doctor info from auth service
        user_info = await get_doctor_from_auth_service(token)
        doctor_id = user_info.get("user_id")

        # Update verification attributes in Keycloak
        verification_attributes = {
            "is_verified": "pending",  # State changes to pending when submitted
            "verification_details": {
                "license_number": request.license_number,
                "license_authority": request.license_authority,
                "license_expiry": request.license_expiry,
                "submitted_at": str(request.submitted_at),
                "documents": request.documents,
            },
        }

        # Call auth service to update user attributes
        auth_url = f"{config.AUTH_SERVICE_URL}/api/auth/users/{doctor_id}/attributes"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.patch(
                auth_url, json=verification_attributes, headers=headers
            )

            if response.status_code != 200:
                logger_service.error(
                    f"Failed to update user attributes: {response.status_code} - {response.text}"
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Verification submission failed",
                )

        # Get updated doctor info from auth service
        auth_url = f"{config.AUTH_SERVICE_URL}/api/auth/users/{doctor_id}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(auth_url, headers=headers)

            if response.status_code != 200:
                logger_service.error(
                    f"Failed to get updated user info: {response.status_code} - {response.text}"
                )

            # Even if we fail to get the updated info, we can still return success
            # We'll just use the basic info from earlier
            doctor_info = response.json() if response.status_code == 200 else None

            # Convert to Doctor model if we have the info
            if doctor_info:
                doctor = Doctor.from_keycloak_data(doctor_info)

        return {
            "message": "Verification submitted successfully. Your documents will be reviewed.",
            "status": "pending",
            "submitted_at": str(request.submitted_at),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error submitting doctor verification: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error submitting verification: {str(e)}"
        )


@router.get(
    "/verification-status",
    response_model=DoctorVerificationInfoResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_verification_status(
        credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Get the current verification status for a doctor"""
    try:
        # Get token from request
        token = credentials.credentials

        # Get doctor info from auth service
        user_info = await get_doctor_from_auth_service(token)
        doctor_id = user_info.get("user_id")

        # Call auth service to get full user profile
        auth_url = f"{config.AUTH_SERVICE_URL}/api/auth/users/{doctor_id}"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(auth_url, headers=headers)

            if response.status_code != 200:
                logger_service.error(
                    f"Failed to get doctor info: {response.status_code} - {response.text}"
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Doctor profile not found",
                )

            doctor_info = response.json()

        # Extract verification information from attributes
        attributes = doctor_info.get("attributes", {})
        is_verified = (
            attributes.get("is_verified", ["false"])[0]
            if isinstance(attributes.get("is_verified", []), list)
            else attributes.get("is_verified", "false")
        )
        verification_details = attributes.get("verification_details", {})

        if isinstance(verification_details, list) and verification_details:
            verification_details = verification_details[0]

        # Convert to expected response format
        return {
            "status": is_verified,
            "submitted_at": (
                verification_details.get("submitted_at")
                if verification_details
                else None
            ),
            "verified_at": (
                verification_details.get("verified_at")
                if verification_details
                else None
            ),
            "license_number": (
                verification_details.get("license_number")
                if verification_details
                else None
            ),
            "license_authority": (
                verification_details.get("license_authority")
                if verification_details
                else None
            ),
            "license_expiry": (
                verification_details.get("license_expiry")
                if verification_details
                else None
            ),
            "rejected_reason": (
                verification_details.get("rejected_reason")
                if verification_details
                else None
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error getting verification status: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving verification status: {str(e)}"
        )


@router.get("/signature")
async def get_doctor_signature(
        credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Get the doctor's digital signature"""
    try:
        # Get token from request
        token = credentials.credentials

        # Get doctor info from auth service
        user_info = await get_doctor_from_auth_service(token)
        doctor_id = user_info.get("user_id")

        # Call auth service to get full user profile
        auth_url = f"{config.AUTH_SERVICE_URL}/api/auth/users/{doctor_id}"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(auth_url, headers=headers)

            if response.status_code != 200:
                logger_service.error(
                    f"Failed to get doctor info: {response.status_code} - {response.text}"
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Doctor profile not found",
                )

            doctor_info = response.json()

        # Get signature from attributes
        attributes = doctor_info.get("attributes", {})
        signature = (
            attributes.get("signature", [""])[0]
            if isinstance(attributes.get("signature", []), list)
            else attributes.get("signature", "")
        )

        if not signature:
            return Response(content="No signature found", status_code=404)

        # Return the signature as an image
        signature_data = base64.b64decode(
            signature.split(",")[1] if "," in signature else signature
        )
        return Response(content=signature_data, media_type="image/png")

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error retrieving doctor signature: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving signature: {str(e)}"
        )


@router.post(
    "/signature",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def update_doctor_signature(
        request: UpdateSignatureRequest,
        credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Update the doctor's digital signature"""
    try:
        # Get token from request
        token = credentials.credentials

        # Get doctor info from auth service
        user_info = await get_doctor_from_auth_service(token)
        doctor_id = user_info.get("user_id")

        # Call auth service to update signature attribute
        auth_url = f"{config.AUTH_SERVICE_URL}/api/auth/users/{doctor_id}/attributes"
        headers = {"Authorization": f"Bearer {token}"}

        # Update attribute
        signature_attributes = {"signature": request.signature_data}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.patch(
                auth_url, json=signature_attributes, headers=headers
            )

            if response.status_code != 200:
                logger_service.error(
                    f"Failed to update signature: {response.status_code} - {response.text}"
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update signature",
                )

        return {"message": "Signature updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error updating doctor signature: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error updating signature: {str(e)}"
        )


@router.post(
    "/upload-profile-picture",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def upload_profile_picture(
        file: UploadFile = File(...),
        credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Upload a profile picture for the doctor"""
    try:
        # Get token from request
        token = credentials.credentials

        # Get doctor info from auth service
        user_info = await get_doctor_from_auth_service(token)
        doctor_id = user_info.get("user_id")

        # Check file format
        if file.content_type not in ["image/jpeg", "image/png", "image/jpg"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid file format. Please upload a JPEG or PNG image.",
            )

        # Read file content
        contents = await file.read()
        if len(contents) > 5 * 1024 * 1024:  # 5MB limit
            raise HTTPException(
                status_code=400, detail="File size too large. Maximum size is 5MB."
            )

        # Convert to base64 for storage in Keycloak
        base64_image = f"data:{file.content_type};base64,{base64.b64encode(contents).decode('utf-8')}"

        # Update profile picture in auth service
        auth_url = f"{config.AUTH_SERVICE_URL}/api/auth/users/{doctor_id}/attributes"
        headers = {"Authorization": f"Bearer {token}"}

        # Update attribute
        profile_attributes = {"profile_picture": base64_image}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.patch(
                auth_url, json=profile_attributes, headers=headers
            )

            if response.status_code != 200:
                logger_service.error(
                    f"Failed to update profile picture: {response.status_code} - {response.text}"
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to upload profile picture",
                )

        return {"message": "Profile picture uploaded successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error uploading profile picture: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error uploading profile picture: {str(e)}"
        )


@router.get(
    "/profile",
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_doctor_profile(
        credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Retrieve doctor's profile information from Keycloak"""
    try:
        # Get token from request
        token = credentials.credentials

        # Get doctor info from auth service
        user_info = await get_doctor_from_auth_service(token)
        doctor_id = user_info.get("user_id")

        # Call auth service to get full user profile
        auth_url = f"{config.AUTH_SERVICE_URL}/api/auth/users/{doctor_id}"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(auth_url, headers=headers)

            if response.status_code != 200:
                logger_service.error(
                    f"Failed to get doctor info: {response.status_code} - {response.text}"
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Doctor profile not found",
                )

            doctor_info = response.json()

        # Convert Keycloak user data format to Doctor model
        doctor = Doctor.from_keycloak_data(doctor_info)
        return doctor.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error retrieving doctor profile: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.put("/profile", response_model=UpdateProfileResponse)
async def update_doctor_profile(
        update_data: DoctorUpdate,
        credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Update doctor's profile information"""
    try:
        # Get token from request
        token = credentials.credentials

        # Get doctor info from auth service
        user_info = await get_doctor_from_auth_service(token)
        doctor_id = user_info.get("user_id")

        # Prepare attributes to update in Keycloak
        attributes = {}

        if update_data.name is not None:
            # Split the name to first and last name for Keycloak
            name_parts = update_data.name.split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""

            # These would be updated separately in Keycloak
            # For now we'll just include them in attributes
            attributes["firstName"] = first_name
            attributes["lastName"] = last_name

        if update_data.specialty is not None:
            attributes["specialty"] = update_data.specialty

        if update_data.phone is not None:
            attributes["phone"] = update_data.phone

        if update_data.address is not None:
            attributes["address"] = update_data.address

        if update_data.profile_picture is not None:
            attributes["profile_picture"] = update_data.profile_picture

        # Add support for new fields
        if update_data.bio is not None:
            attributes["bio"] = update_data.bio

        if update_data.license_number is not None:
            attributes["license_number"] = update_data.license_number

        if update_data.hospital is not None:
            attributes["hospital"] = update_data.hospital

        if update_data.education is not None:
            attributes["education"] = update_data.education

        if update_data.experience is not None:
            attributes["experience"] = update_data.experience

        # Update the user attributes in auth service
        auth_url = f"{config.AUTH_SERVICE_URL}/api/auth/users/{doctor_id}/attributes"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.patch(auth_url, json=attributes, headers=headers)

            if response.status_code != 200:
                logger_service.error(
                    f"Failed to update profile: {response.status_code} - {response.text}"
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update profile",
                )

        # Get updated user info from auth service
        auth_url = f"{config.AUTH_SERVICE_URL}/api/auth/users/{doctor_id}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(auth_url, headers=headers)

            if response.status_code != 200:
                logger_service.error(
                    f"Failed to get updated doctor info: {response.status_code} - {response.text}"
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to retrieve updated profile",
                )

            updated_doctor_info = response.json()
            doctor = Doctor.from_keycloak_data(updated_doctor_info)

        return {"message": "Profile updated successfully", "profile": doctor.to_dict()}

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error updating doctor profile: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating profile: {str(e)}")


@router.get(
    "/",
    response_model=DoctorListResponse,
    responses={500: {"model": ErrorResponse}},
)
async def get_all_doctors(
        specialty: Optional[str] = None,
        name: Optional[str] = None,
        verified_only: bool = False,
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=100),
        user_info: Dict = Depends(get_authenticated_user),
        credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Get all doctors with optional filtering by specialty or name.
    Supports pagination and optional filtering for verified doctors only.
    """
    try:
        # Calculate pagination parameters
        skip = (page - 1) * limit

        # Extract the token from the request for passing to the Auth service
        token = credentials.credentials

        # Set up query parameters for the auth service
        query_params = {"role": "doctor", "first": skip, "max": limit}

        if specialty:
            query_params["specialty"] = specialty

        if name:
            query_params["search"] = name

        # Call auth service directly to get doctors list
        auth_url = f"{config.AUTH_SERVICE_URL}/api/auth/users"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(auth_url, headers=headers, params=query_params)

            if response.status_code != 200:
                logger_service.error(
                    f"Failed to get doctors list: {response.status_code} - {response.text}"
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to retrieve doctors list",
                )

            # Get doctors data from response
            doctors_data = response.json()

        # Process the results
        doctors_list = []
        for user_data in doctors_data:
            # Convert to Doctor model
            doctor = Doctor.from_keycloak_data(user_data)

            # Check if we need to filter by verification status
            attributes = user_data.get("attributes", {})
            is_verified = (
                attributes.get("is_verified", ["false"])[0] == "true"
                if isinstance(attributes.get("is_verified", []), list)
                else attributes.get("is_verified", "false") == "true"
            )

            # Skip if we only want verified doctors and this one isn't
            if verified_only and not is_verified:
                continue

            # Add to results
            doctors_list.append(
                DoctorListItem(
                    id=doctor._id,
                    name=doctor.name,
                    email=doctor.email,
                    specialty=doctor.specialty,
                    phone=doctor.phone,
                    address=doctor.address,
                    profile_picture=getattr(doctor, "profile_picture", None),
                    is_verified=is_verified,
                    bio=getattr(doctor, "bio", None),
                    license_number=getattr(doctor, "license_number", None),
                    hospital=getattr(doctor, "hospital", None),
                    education=getattr(doctor, "education", None),
                    experience=getattr(doctor, "experience", None),
                )
            )

        # Get total for pagination calculation
        total_doctors = len(doctors_list)
        total_pages = (total_doctors + limit - 1) // limit

        return {
            "items": doctors_list[skip: skip + limit],  # Apply pagination
            "total": total_doctors,
            "page": page,
            "pages": total_pages,
        }

    except Exception as e:
        logger_service.error(f"Error retrieving doctors list: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving doctors list: {str(e)}"
        )


@router.get(
    "/{doctor_id}",
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_doctor(
        doctor_id: str, credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get doctor information by ID"""
    try:
        # Get token from request
        token = credentials.credentials

        # Get user info from auth service (without role check)
        user_info = await get_authenticated_user_from_auth_service(token)
        doctor_info = await get_doctor_by_id(doctor_id, token, user_info)

        # At this point doctor_info exists, since get_doctor_by_id raises an exception if not found
        # Check if the viewed profile belongs to a doctor (but don't restrict access)
        roles = doctor_info.get("roles", [])
        if not roles or ("doctor" not in roles and "admin" not in roles):
            logger_service.warning(
                f"Profile {doctor_id} viewed, but doesn't have doctor role"
            )
            # Still return the info as long as it's a valid user profile

        return doctor_info

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error retrieving doctor: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )
