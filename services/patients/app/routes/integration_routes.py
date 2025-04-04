from datetime import datetime
from typing import Dict, Optional

from auth.keycloak_auth import get_current_patient
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from models.patient_model import ErrorResponse, MessageResponse
from services.logger_service import logger_service
from services.mongodb_client import MongoDBClient
from services.rabbitmq_client import RabbitMQClient

from config import Config

router = APIRouter(prefix="/api/integration", tags=["Integration"])

# Initialize services
mongodb_client = MongoDBClient(Config)
rabbitmq_client = RabbitMQClient(Config)

# MongoDB collections
patients_collection = mongodb_client.db.patients
prescriptions_collection = mongodb_client.db.prescriptions
medical_history_collection = mongodb_client.db.medical_history


@router.post(
    "/request-appointment",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def request_appointment(
    doctor_id: str,
    requested_time: str,
    reason: Optional[str] = None,
    user_info: Dict = Depends(get_current_patient),
):
    """Request an appointment with a doctor"""
    try:
        patient_id = user_info.get("user_id")

        # Verify patient exists
        patient = patients_collection.find_one({"_id": ObjectId(patient_id)})
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        # Send appointment request via RabbitMQ
        appointment_id = rabbitmq_client.request_appointment(
            patient_id=patient_id,
            doctor_id=doctor_id,
            requested_time=requested_time,
            reason=reason,
        )

        if appointment_id:
            # Store appointment request in database
            mongodb_client.db.appointment_requests.insert_one(
                {
                    "appointment_id": appointment_id,
                    "patient_id": patient_id,
                    "doctor_id": doctor_id,
                    "requested_time": requested_time,
                    "reason": reason,
                    "status": "requested",
                    "created_at": datetime.utcnow().isoformat(),
                }
            )

            return MessageResponse(
                message=f"Appointment request sent successfully. Appointment ID: {appointment_id}"
            )
        else:
            raise HTTPException(
                status_code=500, detail="Failed to send appointment request"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error requesting appointment: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get(
    "/medical-history",
    responses={500: {"model": ErrorResponse}},
)
async def get_medical_history(user_info: Dict = Depends(get_current_patient)):
    """Get patient's medical history"""
    try:
        patient_id = user_info.get("user_id")

        # Get prescriptions
        prescriptions = list(
            prescriptions_collection.find({"patient_id": patient_id}).sort(
                "created_at", -1
            )
        )

        # Get medical records
        medical_records = list(
            medical_history_collection.find({"patient_id": patient_id}).sort("date", -1)
        )

        # Get radiology reports
        radiology_reports = list(
            mongodb_client.db.radiology_reports.find({"patient_id": patient_id}).sort(
                "created_at", -1
            )
        )

        # Format the data
        formatted_prescriptions = []
        for prescription in prescriptions:
            formatted_prescriptions.append(
                {
                    "id": str(prescription.get("_id")),
                    "doctor_id": prescription.get("doctor_id"),
                    "created_at": prescription.get("created_at"),
                    "status": prescription.get("status"),
                    "medications": prescription.get("medications", []),
                }
            )

        formatted_records = []
        for record in medical_records:
            formatted_records.append(
                {
                    "id": str(record.get("_id")),
                    "type": record.get("type"),
                    "date": record.get("date"),
                    "doctor_id": record.get("doctor_id"),
                    "notes": record.get("notes"),
                    "diagnosis": record.get("diagnosis", []),
                }
            )

        formatted_reports = []
        for report in radiology_reports:
            formatted_reports.append(
                {
                    "id": str(report.get("_id")),
                    "report_id": report.get("report_id"),
                    "exam_type": report.get("exam_type"),
                    "radiologue_id": report.get("radiologue_id"),
                    "doctor_id": report.get("doctor_id"),
                    "created_at": report.get("created_at"),
                    "findings": report.get("findings"),
                    "conclusion": report.get("conclusion"),
                }
            )

        return {
            "prescriptions": formatted_prescriptions,
            "medical_records": formatted_records,
            "radiology_reports": formatted_reports,
        }

    except Exception as e:
        logger_service.error(f"Error retrieving medical history: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get(
    "/prescriptions",
    responses={500: {"model": ErrorResponse}},
)
async def get_prescriptions(user_info: Dict = Depends(get_current_patient)):
    """Get patient's prescriptions"""
    try:
        patient_id = user_info.get("user_id")

        # Get prescriptions
        prescriptions = list(
            prescriptions_collection.find({"patient_id": patient_id}).sort(
                "created_at", -1
            )
        )

        # Format the data
        formatted_prescriptions = []
        for prescription in prescriptions:
            formatted_prescriptions.append(
                {
                    "id": str(prescription.get("_id")),
                    "doctor_id": prescription.get("doctor_id"),
                    "created_at": prescription.get("created_at"),
                    "status": prescription.get("status"),
                    "medications": prescription.get("medications", []),
                }
            )

        return {"prescriptions": formatted_prescriptions}

    except Exception as e:
        logger_service.error(f"Error retrieving prescriptions: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
