from datetime import datetime
from typing import Dict, Optional

from auth.jwt_auth import get_current_user
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from models.api_models import (ErrorResponse, MessageResponse,
                               RadiologyReportRequest, RadiologyReportResponse)
from services.logger_service import logger_service
from services.mongodb_client import MongoDBClient
from services.rabbitmq_client import RabbitMQClient

from config import Config

router = APIRouter(prefix="/api/integration", tags=["Integration"])

# Initialize services
mongodb_client = MongoDBClient(Config)
rabbitmq_client = RabbitMQClient(Config)

# MongoDB collections
radiologues_collection = mongodb_client.db.radiologues
rapports_collection = mongodb_client.db.rapports
requests_collection = mongodb_client.db.examination_requests


@router.post(
    "/accept-examination",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def accept_examination_request(
    request_id: str, user_info: Dict = Depends(get_current_user)
):
    """Accept a radiology examination request"""
    try:
        radiologue_id = user_info.get("user_id")

        # Verify radiologist exists
        radiologue = radiologues_collection.find_one({"_id": ObjectId(radiologue_id)})
        if not radiologue:
            raise HTTPException(status_code=404, detail="Radiologist not found")

        # Find and update the examination request
        request = requests_collection.find_one({"request_id": request_id})
        if not request:
            raise HTTPException(status_code=404, detail="Examination request not found")

        # Update request status to "accepted"
        result = requests_collection.update_one(
            {"request_id": request_id},
            {
                "$set": {
                    "status": "accepted",
                    "radiologue_id": radiologue_id,
                    "accepted_at": datetime.utcnow().isoformat(),
                }
            },
        )

        if result.modified_count > 0:
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
            raise HTTPException(
                status_code=500, detail="Failed to update examination request"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error accepting examination request: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post(
    "/submit-report",
    response_model=RadiologyReportResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def submit_radiology_report(
    report: RadiologyReportRequest, user_info: Dict = Depends(get_current_user)
):
    """Submit a radiology report after examination"""
    try:
        radiologue_id = user_info.get("user_id")

        # Verify radiologist exists
        radiologue = radiologues_collection.find_one({"_id": ObjectId(radiologue_id)})
        if not radiologue:
            raise HTTPException(status_code=404, detail="Radiologist not found")

        # Find the examination request
        request = requests_collection.find_one({"request_id": report.request_id})
        if not request:
            raise HTTPException(status_code=404, detail="Examination request not found")

        # Create the report
        report_id = f"report-{ObjectId()}"
        report_data = {
            "report_id": report_id,
            "request_id": report.request_id,
            "radiologue_id": radiologue_id,
            "doctor_id": request.get("doctor_id"),
            "patient_id": request.get("patient_id"),
            "exam_type": request.get("exam_type"),
            "findings": report.findings,
            "conclusion": report.conclusion,
            "recommendations": report.recommendations,
            "created_at": datetime.utcnow().isoformat(),
            "status": "completed",
        }

        # Insert report into database
        rapports_collection.insert_one(report_data)

        # Update request status
        requests_collection.update_one(
            {"request_id": report.request_id},
            {
                "$set": {
                    "status": "completed",
                    "completed_at": datetime.utcnow().isoformat(),
                    "report_id": report_id,
                }
            },
        )

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
            report_id=report_id, report_data=report_data
        )

        return RadiologyReportResponse(
            report_id=report_id, message="Report submitted successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error submitting radiology report: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get(
    "/examination-requests",
    responses={500: {"model": ErrorResponse}},
)
async def get_examination_requests(
    status: Optional[str] = None, user_info: Dict = Depends(get_current_user)
):
    """Get radiology examination requests"""
    try:
        # Build query
        query = {}
        if status:
            query["status"] = status

        # Get requests from database
        requests = list(requests_collection.find(query).sort("timestamp", -1))

        # Format the response
        formatted_requests = []
        for req in requests:
            formatted_requests.append(
                {
                    "request_id": req.get("request_id"),
                    "doctor_id": req.get("doctor_id"),
                    "patient_id": req.get("patient_id"),
                    "patient_name": req.get("patient_name"),
                    "exam_type": req.get("exam_type"),
                    "reason": req.get("reason"),
                    "urgency": req.get("urgency"),
                    "status": req.get("status"),
                    "timestamp": req.get("timestamp"),
                    "radiologue_id": req.get("radiologue_id", None),
                    "accepted_at": req.get("accepted_at", None),
                    "completed_at": req.get("completed_at", None),
                    "report_id": req.get("report_id", None),
                }
            )

        return {"requests": formatted_requests}

    except Exception as e:
        logger_service.error(f"Error retrieving examination requests: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
