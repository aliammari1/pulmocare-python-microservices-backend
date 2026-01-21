import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import Config
from models.api_models import *
from models.api_models import ErrorResponse, MessageResponse, RadiologyRequestModel
from routes.doctor_routes import (
    get_current_user,
    get_doctor_by_id,
)
from services.appointment_service import AppointmentService
from services.logger_service import logger_service
from services.prescription_service import PrescriptionService
from services.rabbitmq_client import RabbitMQClient
from services.radiology_service import RadiologyService

router = APIRouter(prefix="/api/integration", tags=["Integration"])
security = HTTPBearer()

# Initialize services
rabbitmq_client = RabbitMQClient(Config)


@router.post(
    "/request-radiology",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def request_radiology_examination(request: RadiologyRequestModel, user_info: dict = Depends(get_current_user)):
    """Request a radiology examination for a patient"""
    try:
        doctor_id = user_info.get("user_id")

        # Use auth service to get doctor information
        credentials = HTTPAuthorizationCredentials(credentials=user_info.get("token", ""))
        doctor_info = await get_doctor_by_id(doctor_id, credentials.credentials)

        if not doctor_info:
            raise HTTPException(status_code=404, detail="Doctor not found")

        # Generate a unique request ID
        request_id = f"rad-req-{uuid.uuid4()}"

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
            return MessageResponse(message=f"Radiology examination requested successfully. Request ID: {request_id}")
        else:
            raise HTTPException(status_code=500, detail="Failed to send request to radiology service")

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error requesting radiology examination: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e!s}")


@router.get(
    "/patient-history/{patient_id}",
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_patient_history(patient_id: str, user_info: dict = Depends(get_current_user)):
    """Get a patient's medical history (prescriptions, radiology reports, etc.)"""
    try:
        doctor_id = user_info.get("user_id")

        # Verify doctor exists in auth service
        credentials = HTTPAuthorizationCredentials(credentials=user_info.get("token", ""))
        doctor_info = await get_doctor_by_id(doctor_id, credentials.credentials)
        if not doctor_info:
            raise HTTPException(status_code=404, detail="Doctor not found")

        # Get prescriptions from prescription service
        prescription_service = PrescriptionService()
        prescriptions = await prescription_service.get_prescriptions_for_patient(patient_id=patient_id, doctor_id=doctor_id)

        # Format the prescriptions
        formatted_prescriptions = []
        for prescription in prescriptions.get("items", []):
            formatted_prescriptions.append(
                {
                    "id": prescription.get("id"),
                    "created_at": prescription.get("created_at"),
                    "status": prescription.get("status"),
                    "medications": prescription.get("medications", []),
                }
            )

        # Get radiology reports from radiology service
        radiology_service = RadiologyService()
        radiology_reports = await radiology_service.get_doctor_radiology_reports(doctor_id=doctor_id, patient_id=patient_id)

        # Format the radiology reports
        formatted_reports = []
        for report in radiology_reports.get("items", []):
            formatted_reports.append(
                {
                    "id": report.get("id"),
                    "request_id": report.get("request_id", ""),
                    "exam_type": report.get("exam_type"),
                    "status": report.get("status"),
                    "requested_at": report.get("created_at"),
                    "completed_at": report.get("updated_at"),
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
        raise HTTPException(status_code=500, detail=f"Internal server error: {e!s}")
    finally:
        if prescription_service:
            prescription_service.close()
        if radiology_service:
            radiology_service.close()


@router.post(
    "/notify-patient/{patient_id}",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def notify_patient(
    patient_id: str,
    message: str,
    update_type: str = "general_update",
    user_info: dict = Depends(get_current_user),
):
    """Send a notification to a patient"""
    try:
        doctor_id = user_info.get("user_id")

        # Verify doctor exists in auth service
        credentials = HTTPAuthorizationCredentials(credentials=user_info.get("token", ""))
        doctor_info = await get_doctor_by_id(doctor_id, credentials.credentials)
        if not doctor_info:
            raise HTTPException(status_code=404, detail="Doctor not found")

        # Get doctor's name from auth service
        doctor_name = f"{doctor_info.get('firstName', '')} {doctor_info.get('lastName', '')}".strip()
        if not doctor_name:
            doctor_name = "Unknown Doctor"

        timestamp = datetime.now().isoformat()

        # Send notification via RabbitMQ
        data = {
            "message": message,
            "from_doctor": {
                "id": doctor_id,
                "name": doctor_name,
            },
            "timestamp": timestamp,
        }

        result = rabbitmq_client.notify_patient_medical_update(patient_id=patient_id, update_type=update_type, data=data)

        if result:
            return MessageResponse(message="Patient notification sent successfully")
        else:
            raise HTTPException(status_code=500, detail="Failed to send notification")

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error sending patient notification: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e!s}")


@router.get(
    "/prescriptions",
    response_model=PrescriptionListResponse,
    responses={500: {"model": MessageResponse}},
)
async def get_doctor_prescriptions(
    status: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    user_info: dict = Depends(get_current_user),
):
    """
    Get prescriptions for the current doctor
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create prescription service
        prescription_service = PrescriptionService()

        # Get prescriptions from the prescriptions service
        prescriptions = await prescription_service.get_doctor_prescriptions(doctor_id=doctor_id, status=status, page=page, limit=limit)

        return prescriptions
    except Exception as e:
        logger_service.error(f"Error retrieving doctor prescriptions: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving prescriptions: {e!s}",
        )


@router.get(
    "/prescriptions/{prescription_id}",
    response_model=PrescriptionResponse,
    responses={404: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def get_prescription_details(prescription_id: str, user_info: dict = Depends(get_current_user)):
    """
    Get details for a specific prescription
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create prescription service
        prescription_service = PrescriptionService()

        # Get prescription details
        prescription = await prescription_service.get_prescription_details(prescription_id=prescription_id, doctor_id=doctor_id)

        if not prescription:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prescription not found")

        return prescription
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error retrieving prescription details: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving prescription details: {e!s}",
        )


@router.post(
    "/prescriptions/{prescription_id}/renew",
    response_model=PrescriptionResponse,
    responses={404: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def renew_prescription(prescription_id: str, user_info: dict = Depends(get_current_user)):
    """
    Renew an existing prescription
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create prescription service
        prescription_service = PrescriptionService()

        # Renew the prescription
        new_prescription = await prescription_service.renew_prescription(prescription_id=prescription_id, doctor_id=doctor_id)

        if not new_prescription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Prescription not found or cannot be renewed",
            )

        return new_prescription
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error renewing prescription: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error renewing prescription: {e!s}",
        )


@router.post(
    "/prescriptions/{prescription_id}/cancel",
    response_model=MessageResponse,
    responses={404: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def cancel_prescription(
    prescription_id: str,
    reason: str | None = None,
    user_info: dict = Depends(get_current_user),
):
    """
    Cancel an existing prescription
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create prescription service
        prescription_service = PrescriptionService()

        # Cancel the prescription
        success = await prescription_service.cancel_prescription(prescription_id=prescription_id, doctor_id=doctor_id, reason=reason)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Prescription not found or cannot be cancelled",
            )

        return {"message": "Prescription cancelled successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error cancelling prescription: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error cancelling prescription: {e!s}",
        )


@router.get(
    "/appointments",
    response_model=AppointmentListResponse,
    responses={500: {"model": MessageResponse}},
)
async def get_doctor_appointments(
    status: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    doctor_id: str | None = None,
    user_info: dict = Depends(get_current_user),
):
    """
    Get appointments for the current doctor
    """
    try:
        # Create appointment service
        appointment_service = AppointmentService()

        # Get appointments
        appointments = await appointment_service.get_doctor_appointments(doctor_id=doctor_id, status=status, page=page, limit=limit)

        return appointments
    except Exception as e:
        logger_service.error(f"Error retrieving doctor appointments: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving appointments: {e!s}",
        )
    finally:
        if appointment_service:
            appointment_service.close()


@router.get(
    "/appointments/{appointment_id}",
    response_model=AppointmentResponse,
    responses={404: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def get_appointment_details(appointment_id: str, user_info: dict = Depends(get_current_user)):
    """
    Get details for a specific appointment
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create appointment service
        appointment_service = AppointmentService()

        # Get appointment details
        appointment = await appointment_service.get_appointment_details(appointment_id=appointment_id, doctor_id=doctor_id)

        if not appointment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

        return appointment
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error retrieving appointment details: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving appointment details: {e!s}",
        )


@router.post(
    "/appointments/{appointment_id}/accept",
    response_model=AppointmentResponse,
    responses={404: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def accept_appointment(appointment_id: str, user_info: dict = Depends(get_current_user)):
    """
    Accept an appointment request
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create appointment service
        appointment_service = AppointmentService()

        # Accept the appointment
        updated_appointment = await appointment_service.update_appointment_status(appointment_id=appointment_id, doctor_id=doctor_id, new_status="accepted")

        if not updated_appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found or cannot be accepted",
            )

        return updated_appointment
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error accepting appointment: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error accepting appointment: {e!s}",
        )


@router.post(
    "/appointments/{appointment_id}/reject",
    response_model=AppointmentResponse,
    responses={404: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def reject_appointment(
    appointment_id: str,
    reason: str | None = None,
    user_info: dict = Depends(get_current_user),
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
        logger_service.error(f"Error rejecting appointment: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error rejecting appointment: {e!s}",
        )


@router.get(
    "/radiology-reports",
    response_model=RadiologyReportsListResponse,
    responses={500: {"model": MessageResponse}},
)
async def get_doctor_radiology_reports(
    patient_id: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    user_info: dict = Depends(get_current_user),
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
        logger_service.error(f"Error retrieving radiology reports: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving radiology reports: {e!s}",
        )


@router.get(
    "/radiology-reports/{report_id}",
    response_model=RadiologyReportResponse,
    responses={404: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def get_radiology_report_details(report_id: str, user_info: dict = Depends(get_current_user)):
    """
    Get details for a specific radiology report
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create radiology service
        radiology_service = RadiologyService()

        # Get report details
        report = await radiology_service.get_radiology_report_details(report_id=report_id, doctor_id=doctor_id)

        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Radiology report not found",
            )

        return report
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error retrieving radiology report details: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving radiology report details: {e!s}",
        )


@router.post(
    "/radiology-requests",
    response_model=MessageResponse,
    responses={400: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def request_radiology_examination(
    patient_id: str,
    exam_type: str,
    reason: str | None = None,
    urgency: str = "normal",
    user_info: dict = Depends(get_current_user),
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

        return {"message": f"Radiology examination request created with ID: {request_id}"}
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error creating radiology examination request: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating radiology examination request: {e!s}",
        )


# New Radiology endpoints


@router.get(
    "/radiology/reports",
    response_model=RadiologyReportsListResponse,
    responses={500: {"model": MessageResponse}},
)
async def get_doctor_radiology_reports(
    status: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    user_info: dict = Depends(get_current_user),
):
    """
    Get radiology reports for the current doctor
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create radiology service
        radiology_service = RadiologyService()

        # Get radiology reports from the radiology service
        reports = await radiology_service.get_doctor_radiology_reports(doctor_id=doctor_id, status=status, page=page, limit=limit)

        return reports
    except Exception as e:
        logger_service.error(f"Error retrieving doctor radiology reports: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving radiology reports: {e!s}",
        )
    finally:
        if radiology_service:
            radiology_service.close()


@router.get(
    "/radiology/reports/{report_id}",
    response_model=RadiologyReportResponse,
    responses={404: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def get_radiology_report_details(report_id: str, user_info: dict = Depends(get_current_user)):
    """
    Get details for a specific radiology report
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create radiology service
        radiology_service = RadiologyService()

        # Get report details
        report = await radiology_service.get_radiology_report_details(report_id=report_id)

        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Radiology report not found",
            )

        # Check if this report belongs to the current doctor
        if "doctor_id" in report and report["doctor_id"] and report["doctor_id"] != doctor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view this report",
            )

        return report
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error retrieving radiology report details: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving radiology report details: {e!s}",
        )
    finally:
        if radiology_service:
            radiology_service.close()


@router.post(
    "/radiology/examinations",
    response_model=RadiologyExaminationResponse,
    responses={400: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def request_radiology_examination(request: RadiologyExaminationRequest, user_info: dict = Depends(get_current_user)):
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
        logger_service.error(f"Error requesting radiology examination: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error requesting radiology examination: {e!s}",
        )
    finally:
        if radiology_service:
            radiology_service.close()


@router.post(
    "/appointments/{appointment_id}/cancel",
    response_model=AppointmentResponse,
    responses={404: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def cancel_appointment(
    appointment_id: str,
    reason: str | None = None,
    user_info: dict = Depends(get_current_user),
):
    """
    Cancel an existing appointment
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create appointment service
        appointment_service = AppointmentService()

        # Cancel the appointment
        updated_appointment = await appointment_service.cancel_appointment(appointment_id=appointment_id, doctor_id=doctor_id, reason=reason)

        if not updated_appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found or cannot be cancelled",
            )

        return updated_appointment
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error cancelling appointment: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error cancelling appointment: {e!s}",
        )
    finally:
        if appointment_service:
            appointment_service.close()


@router.post(
    "/appointments/{appointment_id}/reschedule",
    response_model=AppointmentResponse,
    responses={404: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def reschedule_appointment(
    appointment_id: str,
    new_time: str,
    reason: str | None = None,
    user_info: dict = Depends(get_current_user),
):
    """
    Reschedule an appointment to a new time
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create appointment service
        appointment_service = AppointmentService()

        # Reschedule the appointment
        updated_appointment = await appointment_service.reschedule_appointment(
            appointment_id=appointment_id,
            doctor_id=doctor_id,
            new_time=new_time,
            reason=reason,
        )

        if not updated_appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found or cannot be rescheduled",
            )

        return updated_appointment
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error rescheduling appointment: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error rescheduling appointment: {e!s}",
        )
    finally:
        if appointment_service:
            appointment_service.close()


@router.post(
    "/appointments/{appointment_id}/notes",
    response_model=AppointmentResponse,
    responses={404: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def add_appointment_notes(
    appointment_id: str,
    notes: str,
    user_info: dict = Depends(get_current_user),
):
    """
    Add notes to an existing appointment
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create appointment service
        appointment_service = AppointmentService()

        # Add notes to the appointment
        updated_appointment = await appointment_service.add_appointment_notes(appointment_id=appointment_id, doctor_id=doctor_id, notes=notes)

        if not updated_appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found or notes cannot be added",
            )

        return updated_appointment
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error adding appointment notes: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error adding appointment notes: {e!s}",
        )
    finally:
        if appointment_service:
            appointment_service.close()


@router.post(
    "/appointments/{appointment_id}/complete",
    response_model=AppointmentResponse,
    responses={404: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def complete_appointment(
    appointment_id: str,
    notes: str | None = None,
    user_info: dict = Depends(get_current_user),
):
    """
    Mark an appointment as completed
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create appointment service
        appointment_service = AppointmentService()

        # Complete the appointment
        updated_appointment = await appointment_service.complete_appointment(appointment_id=appointment_id, doctor_id=doctor_id, notes=notes)

        if not updated_appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found or cannot be completed",
            )

        return updated_appointment
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error completing appointment: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error completing appointment: {e!s}",
        )
    finally:
        if appointment_service:
            appointment_service.close()


@router.get(
    "/patient/{patient_id}/appointments",
    response_model=AppointmentListResponse,
    responses={500: {"model": MessageResponse}},
)
async def get_patient_appointments(
    patient_id: str,
    status: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    user_info: dict = Depends(get_current_user),
):
    """
    Get appointments between the current doctor and a specific patient
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create appointment service
        appointment_service = AppointmentService()

        # Get patient appointments
        appointments = await appointment_service.get_patient_appointments(
            doctor_id=doctor_id,
            patient_id=patient_id,
            status=status,
            page=page,
            limit=limit,
        )

        return appointments
    except Exception as e:
        logger_service.error(f"Error retrieving patient appointments: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving patient appointments: {e!s}",
        )
    finally:
        if appointment_service:
            appointment_service.close()


@router.post(
    "/create-appointment",
    response_model=AppointmentResponse,
    responses={400: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def create_appointment(
    patient_id: str,
    patient_name: str,
    requested_time: str,
    reason: str | None = None,
    user_info: dict = Depends(get_current_user),
):
    """
    Create a new appointment for a patient with this doctor
    """
    try:
        doctor_id = user_info.get("user_id")

        # Create appointment service
        appointment_service = AppointmentService()

        # Create the appointment
        new_appointment = await appointment_service.create_appointment(
            doctor_id=doctor_id,
            patient_id=patient_id,
            patient_name=patient_name,
            requested_time=requested_time,
            reason=reason,
        )

        if not new_appointment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create appointment",
            )

        return new_appointment
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error creating appointment: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating appointment: {e!s}",
        )
    finally:
        if appointment_service:
            appointment_service.close()


# New direct API endpoint to serve appointments for AppointmentService
@router.get(
    "/appointments/doctor/{doctor_id}",
    response_model=AppointmentListResponse,
    responses={404: {"model": MessageResponse}, 500: {"model": MessageResponse}},
)
async def get_doctor_appointments_direct(
    doctor_id: str,
    status: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    user_info: dict = Depends(get_current_user),
):
    """
    Get appointments for a specific doctor (direct API endpoint for service-to-service calls)
    """
    try:
        # Verify the requesting user is authorized (either the doctor themselves or an admin)
        if user_info.get("user_id") != doctor_id and "admin" not in user_info.get("roles", []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view these appointments",
            )

        # Verify doctor exists in auth service
        credentials = HTTPAuthorizationCredentials(credentials=user_info.get("token", ""))
        doctor_info = await get_doctor_by_id(doctor_id, credentials.credentials)
        if not doctor_info:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

        # Create appointment service
        appointment_service = AppointmentService()

        # Get appointments from the appointment service
        appointments = await appointment_service.get_doctor_appointments(doctor_id=doctor_id, status=status, page=page, limit=limit)

        return appointments
    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error retrieving doctor appointments: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving appointments: {e!s}",
        )
    finally:
        if appointment_service:
            appointment_service.close()
