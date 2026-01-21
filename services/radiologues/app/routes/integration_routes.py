from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import Config
from models.api_models import ErrorResponse, RadiologyReportResponse
from services.logger_service import logger_service

# Create HTTPBearer instance
security = HTTPBearer()

from models.api_models import (
    MessageResponse,
    RadiologyReportRequest,
)
from services.rabbitmq_client import RabbitMQClient

router = APIRouter(prefix="/api/integration", tags=["Integration"])
http_client = httpx.AsyncClient(timeout=30.0)

# Initialize services
config = Config()
rabbitmq_client = RabbitMQClient(Config)


# Authentication service client functions
async def get_current_radiologist(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
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
                logger_service.error(f"Failed to verify token: {response.status_code} - {response.text}")
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
        logger_service.error(f"Error connecting to auth service: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Unexpected error during authentication: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication error",
        )


async def get_user_info(user_id: str, token: str = None) -> dict:
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
                logger_service.error(f"Failed to get user info: {response.status_code} - {response.text}")
                if response.status_code == 404:
                    return None
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Failed to get user information",
                )

            return response.json()
    except httpx.RequestError as e:
        logger_service.error(f"Error connecting to auth service: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error getting user info: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user information: {e!s}",
        )


# Reports service client functions
async def get_examination_requests_from_service(status: str | None = None, token: str = None) -> dict:
    """
    Get examination requests from the reports service

    Args:
        status: Filter by status
        token: Auth token

    Returns:
        Dict with requests list
    """
    try:
        reports_url = f"{Config.REPORTS_SERVICE_URL}/api/integration/examination-requests"

        # Build query params
        params = {}
        if status:
            params["status"] = status

        # Set headers if token is provided
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        # Get requests from reports service
        async with http_client as client:
            response = await client.get(reports_url, params=params, headers=headers)

            if response.status_code != 200:
                logger_service.error(f"Failed to get examination requests: {response.status_code} - {response.text}")
                # Return empty results on error
                return {"requests": []}

            return response.json()

    except httpx.RequestError as e:
        logger_service.error(f"Error connecting to reports service: {e!s}")
        return {"requests": []}
    except Exception as e:
        logger_service.error(f"Error getting examination requests: {e!s}")
        return {"requests": []}


async def update_examination_request_in_service(request_id: str, update_data: dict, token: str) -> bool:
    """
    Update examination request status in the reports service

    Args:
        request_id: ID of the request to update
        update_data: Data to update
        token: Auth token

    Returns:
        Success status
    """
    try:
        reports_url = f"{Config.REPORTS_SERVICE_URL}/api/integration/examination-requests/{request_id}"

        # Set headers with token
        headers = {"Authorization": f"Bearer {token}"}

        # Update request in reports service
        async with http_client as client:
            response = await client.patch(reports_url, json=update_data, headers=headers)

            if response.status_code != 200:
                logger_service.error(f"Failed to update examination request: {response.status_code} - {response.text}")
                return False

            return True

    except httpx.RequestError as e:
        logger_service.error(f"Error connecting to reports service: {e!s}")
        return False
    except Exception as e:
        logger_service.error(f"Error updating examination request: {e!s}")
        return False


async def submit_radiology_report_to_service(report_data: dict, token: str) -> dict | None:
    """
    Submit a radiology report to the reports service

    Args:
        report_data: Report data
        token: Auth token

    Returns:
        Created report data or None if submission failed
    """
    try:
        reports_url = f"{Config.REPORTS_SERVICE_URL}/api/integration/submit-report"

        # Set headers with token
        headers = {"Authorization": f"Bearer {token}"}

        # Submit report to reports service
        async with http_client as client:
            response = await client.post(reports_url, json=report_data, headers=headers)

            if response.status_code != 201:
                logger_service.error(f"Failed to submit report: {response.status_code} - {response.text}")
                return None

            return response.json()

    except httpx.RequestError as e:
        logger_service.error(f"Error connecting to reports service: {e!s}")
        return None
    except Exception as e:
        logger_service.error(f"Error submitting report: {e!s}")
        return None


@router.post(
    "/accept-examination",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def accept_examination_request(request_id: str, user_info: dict = Depends(get_current_radiologist)):
    """Accept a radiology examination request"""
    try:
        radiologue_id = user_info.get("user_id")
        token = user_info.get("token")

        # Get radiologist info from auth service
        radiologue_data = await get_user_info(radiologue_id, token)
        if not radiologue_data:
            raise HTTPException(status_code=404, detail="Radiologist not found")

        # Find the examination request
        reports_url = f"{Config.REPORTS_SERVICE_URL}/api/integration/examination-requests/{request_id}"
        headers = {"Authorization": f"Bearer {token}"}

        async with http_client as client:
            response = await client.get(reports_url, headers=headers)

            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Examination request not found")

            if response.status_code != 200:
                raise HTTPException(status_code=500, detail="Failed to retrieve examination request")

            request = response.json()

        # Update request status to "accepted"
        update_data = {
            "status": "accepted",
            "radiologue_id": radiologue_id,
            "accepted_at": datetime.utcnow().isoformat(),
        }

        success = await update_examination_request_in_service(request_id, update_data, token)

        if success:
            # Notify doctor via RabbitMQ
            rabbitmq_client.publish_message(
                exchange="medical.reports",
                routing_key="report.examination.accepted",
                message={
                    "request_id": request_id,
                    "doctor_id": request.get("doctor_id"),
                    "patient_id": request.get("patient_id"),
                    "radiologue_id": radiologue_id,
                    "status": "accepted",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

            return MessageResponse(message="Examination request accepted successfully")
        else:
            raise HTTPException(status_code=500, detail="Failed to update examination request")

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error accepting examination request: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e!s}")


@router.post(
    "/submit-report",
    response_model=RadiologyReportResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def submit_radiology_report(report: RadiologyReportRequest, user_info: dict = Depends(get_current_radiologist)):
    """Submit a radiology report after examination"""
    try:
        radiologue_id = user_info.get("user_id")
        token = user_info.get("token")

        # Get radiologist info from auth service
        radiologue_data = await get_user_info(radiologue_id, token)
        if not radiologue_data:
            raise HTTPException(status_code=404, detail="Radiologist not found")

        radiologue_name = radiologue_data.get("name", "Unknown Radiologist")

        # Find the examination request
        reports_url = f"{Config.REPORTS_SERVICE_URL}/api/integration/examination-requests/{report.request_id}"
        headers = {"Authorization": f"Bearer {token}"}

        async with http_client as client:
            response = await client.get(reports_url, headers=headers)

            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Examination request not found")

            if response.status_code != 200:
                raise HTTPException(status_code=500, detail="Failed to retrieve examination request")

            request = response.json()

        # Create the report data
        report_data = {
            "request_id": report.request_id,
            "radiologist_id": radiologue_id,
            "radiologist_name": radiologue_name,
            "doctor_id": request.get("doctor_id"),
            "patient_id": request.get("patient_id"),
            "patient_name": request.get("patient_name"),
            "exam_type": request.get("exam_type"),
            "findings": report.findings,
            "conclusion": report.conclusion,
            "recommendations": report.recommendations,
            "status": "completed",
        }

        # Submit report to reports service
        created_report = await submit_radiology_report_to_service(report_data, token)

        if not created_report:
            raise HTTPException(status_code=500, detail="Failed to create report")

        report_id = created_report.get("id") or created_report.get("report_id")

        if not report_id:
            raise HTTPException(status_code=500, detail="Invalid report data returned")

        # Update request status to completed
        update_data = {
            "status": "completed",
            "completed_at": datetime.utcnow().isoformat(),
            "report_id": report_id,
        }

        await update_examination_request_in_service(report.request_id, update_data, token)

        # Notify about completed examination
        rabbitmq_client.publish_examination_result(
            request_id=report.request_id,
            doctor_id=request.get("doctor_id"),
            patient_id=request.get("patient_id"),
            exam_type=request.get("exam_type"),
            report_id=report_id,
        )

        # Also send the report for analysis
        rabbitmq_client.publish_radiology_report(
            report_id=report_id,
            report_data={
                **report_data,
                "id": report_id,
                "created_at": datetime.utcnow().isoformat(),
            },
        )

        # Notify the doctor that the report is ready
        rabbitmq_client.notify_doctor_report_ready(
            report_id=report_id,
            doctor_id=request.get("doctor_id"),
            patient_id=request.get("patient_id"),
            exam_type=request.get("exam_type"),
        )

        return RadiologyReportResponse(report_id=report_id, message="Report submitted successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error submitting radiology report: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e!s}")


@router.get(
    "/examination-requests",
    responses={500: {"model": ErrorResponse}},
)
async def get_examination_requests(status: str | None = None, user_info: dict = Depends(get_current_radiologist)):
    """Get radiology examination requests"""
    try:
        token = user_info.get("token")

        # Get examination requests from the reports service
        result = await get_examination_requests_from_service(status, token)

        return result

    except Exception as e:
        logger_service.error(f"Error retrieving examination requests: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e!s}")
