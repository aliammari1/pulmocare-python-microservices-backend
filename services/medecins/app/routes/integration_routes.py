from typing import Dict, Optional

from auth.keycloak_auth import get_current_user
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from models.api_models import *
from models.api_models import (ErrorResponse, MessageResponse,
                               RadiologyRequestModel)
from services.appointment_service import AppointmentService
from services.logger_service import logger_service
from services.mongodb_client import MongoDBClient
from services.prescription_service import PrescriptionService
from services.rabbitmq_client import RabbitMQClient
from services.radiology_service import RadiologyService

from config import Config

router = APIRouter(prefix="/api/integration", tags=["Integration"])

# Initialize services
mongodb_client = MongoDBClient(Config)
rabbitmq_client = RabbitMQClient(Config)

# MongoDB collections
doctors_collection = mongodb_client.db.doctors


@router.post(
    "/request-radiology",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def request_radiology_examination(
    request: RadiologyRequestModel, user_info: Dict = Depends(get_current_user)
):
    """Request a radiology examination for a patient"""
    try:
        doctor_id = user_info.get("user_id")
        doctor = doctors_collection.find_one({"_id": ObjectId(doctor_id)})

        if not doctor:
            raise HTTPException(status_code=404, detail="Doctor not found")

        # Generate a unique request ID
        request_id = f"rad-req-{ObjectId()}"

        # Send the request to the radiology service via RabbitMQ
        result = rabbitmq_client.request_radiology_examination(
            request_id=request_id,
            doctor_id=doctor_id,
            patient_id=request.patient_id,
            patient_name=request.patient_name,
            exam_type=request.exam_type,
            reason=request.reason,
            urgency=request.urgency,
        )

        if result:
            return MessageResponse(
                message=f"Radiology examination requested successfully. Request ID: {request_id}"
            )
        else:
            raise HTTPException(
                status_code=500, detail="Failed to send request to radiology service"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error requesting radiology examination: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get(
    "/patient-history/{patient_id}",
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_patient_history(
    patient_id: str, user_info: Dict = Depends(get_current_user)
):
    """Get a patient's medical history (prescriptions, radiology reports, etc.)"""
    try:
        doctor_id = user_info.get("user_id")

        # Verify doctor exists
        doctor = doctors_collection.find_one({"_id": ObjectId(doctor_id)})
        if not doctor:
            raise HTTPException(status_code=404, detail="Doctor not found")

        # Get prescriptions for this patient from local database
        prescriptions = list(
            mongodb_client.db.prescriptions.find(
                {"patient_id": patient_id, "doctor_id": doctor_id}
            )
        )

        # Format the prescriptions
        formatted_prescriptions = []
        for prescription in prescriptions:
            formatted_prescriptions.append(
                {
                    "id": str(prescription["_id"]),
                    "created_at": prescription.get("created_at"),
                    "status": prescription.get("status"),
                    "medications": prescription.get("medications", []),
                }
            )

        # Get radiology reports for this patient
        radiology_reports = list(
            mongodb_client.db.radiology_requests.find(
                {"patient_id": patient_id, "doctor_id": doctor_id}
            )
        )

        # Format the radiology reports
        formatted_reports = []
        for report in radiology_reports:
            formatted_reports.append(
                {
                    "id": str(report["_id"]),
                    "request_id": report.get("request_id"),
                    "exam_type": report.get("exam_type"),
                    "status": report.get("status"),
                    "requested_at": report.get("timestamp"),
                    "completed_at": report.get("completed_at"),
                }
            )

        return {
            "patient_id": patient_id,
            "prescriptions": formatted_prescriptions,
            "radiology_reports": formatted_reports,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error retrieving patient history: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post(
    "/notify-patient/{patient_id}",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def notify_patient(
    patient_id: str,
    message: str,
    update_type: str = "general_update",
    user_info: Dict = Depends(get_current_user),
):
    """Send a notification to a patient"""
    try:
        doctor_id = user_info.get("user_id")

        # Verify doctor exists
        doctor = doctors_collection.find_one({"_id": ObjectId(doctor_id)})
        if not doctor:
            raise HTTPException(status_code=404, detail="Doctor not found")

        # Send notification via RabbitMQ
        data = {
            "message": message,
            "from_doctor": {
                "id": doctor_id,
                "name": doctor.get("name", "Unknown Doctor"),
            },
            "timestamp": str(ObjectId().generation_time),
        }

        result = rabbitmq_client.notify_patient_medical_update(
            patient_id=patient_id, update_type=update_type, data=data
        )

        if result:
            return MessageResponse(message="Patient notification sent successfully")
        else:
            raise HTTPException(status_code=500, detail="Failed to send notification")

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error sending patient notification: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get(
    "/prescriptions",
    response_model=PrescriptionListResponse,
    responses={500: {"model": MessageResponse}},
)
async def get_doctor_prescriptions(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    user_info: Dict = Depends(get_current_user),
):
    """
    Get prescriptions for the current doctor
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create prescription service
        prescription_service = PrescriptionService()

        # Get prescriptions from the prescriptions service
        prescriptions = await prescription_service.get_doctor_prescriptions(
            doctor_id=doctor_id, status=status, page=page, limit=limit
        )

        return prescriptions
    except Exception as e:
        logger_service.error(f"Error retrieving doctor prescriptions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving prescriptions: {str(e)}",
        )


@router.get(
    "/prescriptions/{prescription_id}",
    response_model=PrescriptionResponse,
    responses={404: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def get_prescription_details(
    prescription_id: str, user_info: Dict = Depends(get_current_user)
):
    """
    Get details for a specific prescription
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create prescription service
        prescription_service = PrescriptionService()

        # Get prescription details
        prescription = await prescription_service.get_prescription_details(
            prescription_id=prescription_id, doctor_id=doctor_id
        )

        if not prescription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Prescription not found"
            )

        return prescription
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error retrieving prescription details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving prescription details: {str(e)}",
        )


@router.post(
    "/prescriptions/{prescription_id}/renew",
    response_model=PrescriptionResponse,
    responses={404: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def renew_prescription(
    prescription_id: str, user_info: Dict = Depends(get_current_user)
):
    """
    Renew an existing prescription
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create prescription service
        prescription_service = PrescriptionService()

        # Renew the prescription
        new_prescription = await prescription_service.renew_prescription(
            prescription_id=prescription_id, doctor_id=doctor_id
        )

        if not new_prescription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Prescription not found or cannot be renewed",
            )

        return new_prescription
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error renewing prescription: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error renewing prescription: {str(e)}",
        )


@router.post(
    "/prescriptions/{prescription_id}/cancel",
    response_model=MessageResponse,
    responses={404: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def cancel_prescription(
    prescription_id: str,
    reason: Optional[str] = None,
    user_info: Dict = Depends(get_current_user),
):
    """
    Cancel an existing prescription
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create prescription service
        prescription_service = PrescriptionService()

        # Cancel the prescription
        success = await prescription_service.cancel_prescription(
            prescription_id=prescription_id, doctor_id=doctor_id, reason=reason
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Prescription not found or cannot be cancelled",
            )

        return {"message": "Prescription cancelled successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error cancelling prescription: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error cancelling prescription: {str(e)}",
        )


@router.get(
    "/appointments",
    response_model=AppointmentListResponse,
    responses={500: {"model": MessageResponse}},
)
async def get_doctor_appointments(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    user_info: Dict = Depends(get_current_user),
):
    """
    Get appointments for the current doctor
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create appointment service
        appointment_service = AppointmentService()

        # Get appointments
        appointments = await appointment_service.get_doctor_appointments(
            doctor_id=doctor_id, status=status, page=page, limit=limit
        )

        return appointments
    except Exception as e:
        logger_service.error(f"Error retrieving doctor appointments: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving appointments: {str(e)}",
        )


@router.get(
    "/appointments/{appointment_id}",
    response_model=AppointmentResponse,
    responses={404: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def get_appointment_details(
    appointment_id: str, user_info: Dict = Depends(get_current_user)
):
    """
    Get details for a specific appointment
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create appointment service
        appointment_service = AppointmentService()

        # Get appointment details
        appointment = await appointment_service.get_appointment_details(
            appointment_id=appointment_id, doctor_id=doctor_id
        )

        if not appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found"
            )

        return appointment
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error retrieving appointment details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving appointment details: {str(e)}",
        )


@router.post(
    "/appointments/{appointment_id}/accept",
    response_model=AppointmentResponse,
    responses={404: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def accept_appointment(
    appointment_id: str, user_info: Dict = Depends(get_current_user)
):
    """
    Accept an appointment request
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create appointment service
        appointment_service = AppointmentService()

        # Accept the appointment
        updated_appointment = await appointment_service.update_appointment_status(
            appointment_id=appointment_id, doctor_id=doctor_id, new_status="accepted"
        )

        if not updated_appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found or cannot be accepted",
            )

        return updated_appointment
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error accepting appointment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error accepting appointment: {str(e)}",
        )


@router.post(
    "/appointments/{appointment_id}/reject",
    response_model=AppointmentResponse,
    responses={404: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def reject_appointment(
    appointment_id: str,
    reason: Optional[str] = None,
    user_info: Dict = Depends(get_current_user),
):
    """
    Reject an appointment request
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create appointment service
        appointment_service = AppointmentService()

        # Reject the appointment
        updated_appointment = await appointment_service.update_appointment_status(
            appointment_id=appointment_id,
            doctor_id=doctor_id,
            new_status="rejected",
            reason=reason,
        )

        if not updated_appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found or cannot be rejected",
            )

        return updated_appointment
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error rejecting appointment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error rejecting appointment: {str(e)}",
        )


@router.get(
    "/radiology-reports",
    response_model=RadiologyReportsListResponse,
    responses={500: {"model": MessageResponse}},
)
async def get_doctor_radiology_reports(
    patient_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    user_info: Dict = Depends(get_current_user),
):
    """
    Get radiology reports related to the current doctor
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create radiology service
        radiology_service = RadiologyService()

        # Get reports from the radiology service
        reports = await radiology_service.get_doctor_radiology_reports(
            doctor_id=doctor_id,
            patient_id=patient_id,
            status=status,
            page=page,
            limit=limit,
        )

        return reports
    except Exception as e:
        logger_service.error(f"Error retrieving radiology reports: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving radiology reports: {str(e)}",
        )


@router.get(
    "/radiology-reports/{report_id}",
    response_model=RadiologyReportResponse,
    responses={404: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def get_radiology_report_details(
    report_id: str, user_info: Dict = Depends(get_current_user)
):
    """
    Get details for a specific radiology report
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create radiology service
        radiology_service = RadiologyService()

        # Get report details
        report = await radiology_service.get_radiology_report_details(
            report_id=report_id, doctor_id=doctor_id
        )

        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Radiology report not found",
            )

        return report
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error retrieving radiology report details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving radiology report details: {str(e)}",
        )


@router.post(
    "/radiology-requests",
    response_model=MessageResponse,
    responses={400: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def request_radiology_examination(
    patient_id: str,
    exam_type: str,
    reason: Optional[str] = None,
    urgency: str = "normal",
    user_info: Dict = Depends(get_current_user),
):
    """
    Request a radiology examination for a patient
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create radiology service
        radiology_service = RadiologyService()

        # Request examination
        request_id = await radiology_service.request_radiology_examination(
            doctor_id=doctor_id,
            patient_id=patient_id,
            exam_type=exam_type,
            reason=reason,
            urgency=urgency,
        )

        if not request_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create radiology examination request",
            )

        return {
            "message": f"Radiology examination request created with ID: {request_id}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error creating radiology examination request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating radiology examination request: {str(e)}",
        )


# New Radiology endpoints


@router.get(
    "/radiology/reports",
    response_model=RadiologyReportsListResponse,
    responses={500: {"model": MessageResponse}},
)
async def get_doctor_radiology_reports(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    user_info: Dict = Depends(get_current_user),
):
    """
    Get radiology reports for the current doctor
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create radiology service
        radiology_service = RadiologyService()

        # Get radiology reports from the radiology service
        reports = await radiology_service.get_doctor_radiology_reports(
            doctor_id=doctor_id, status=status, page=page, limit=limit
        )

        return reports
    except Exception as e:
        logger_service.error(f"Error retrieving doctor radiology reports: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving radiology reports: {str(e)}",
        )
    finally:
        if radiology_service:
            radiology_service.close()


@router.get(
    "/radiology/reports/{report_id}",
    response_model=RadiologyReportResponse,
    responses={404: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def get_radiology_report_details(
    report_id: str, user_info: Dict = Depends(get_current_user)
):
    """
    Get details for a specific radiology report
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create radiology service
        radiology_service = RadiologyService()

        # Get report details
        report = await radiology_service.get_radiology_report_details(
            report_id=report_id
        )

        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Radiology report not found",
            )

        # Check if this report belongs to the current doctor
        if (
            "doctor_id" in report
            and report["doctor_id"]
            and report["doctor_id"] != doctor_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view this report",
            )

        return report
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error retrieving radiology report details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving radiology report details: {str(e)}",
        )
    finally:
        if radiology_service:
            radiology_service.close()


@router.post(
    "/radiology/examinations",
    response_model=RadiologyExaminationResponse,
    responses={400: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def request_radiology_examination(
    request: RadiologyExaminationRequest, user_info: Dict = Depends(get_current_user)
):
    """
    Request a radiology examination for a patient
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create radiology service
        radiology_service = RadiologyService()

        # Request the examination
        examination = await radiology_service.request_radiology_examination(
            doctor_id=doctor_id,
            patient_id=request.patient_id,
            patient_name=request.patient_name,
            exam_type=request.exam_type,
            reason=request.reason,
            urgency=request.urgency,
        )

        if not examination:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to request radiology examination",
            )

        return examination
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error requesting radiology examination: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error requesting radiology examination: {str(e)}",
        )
    finally:
        if radiology_service:
            radiology_service.close()
