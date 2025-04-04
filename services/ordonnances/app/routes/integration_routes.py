from datetime import datetime
from typing import Dict, Optional

from auth.keycloak_auth import get_current_doctor
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from models.api_models import ErrorResponse, MessageResponse
from models.ordonnance import OrdonnanceCreate
from services.logger_service import logger_service
from services.mongodb_client import MongoDBClient
from services.pdf_service import generate_ordonnance_pdf
from services.rabbitmq_client import RabbitMQClient

from config import Config

router = APIRouter(prefix="/api/integration", tags=["Integration"])

# Initialize services
mongodb_client = MongoDBClient(Config)
rabbitmq_client = RabbitMQClient(Config)

# MongoDB collections
ordonnances_collection = mongodb_client.db.ordonnances


@router.post(
    "/create-prescription",
    response_model=Dict[str, str],
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def create_prescription(
    prescription: OrdonnanceCreate, user_info: Dict = Depends(get_current_doctor)
):
    """Create a new prescription and notify relevant services"""
    try:
        doctor_id = user_info.get("user_id")

        # Create ordonnance document
        ordonnance_data = {
            "patient_id": prescription.patient_id,
            "patient_name": prescription.patient_name,
            "medecin_id": doctor_id,
            "medicaments": [med.dict() for med in prescription.medicaments],
            "date_creation": datetime.utcnow().isoformat(),
            "date_expiration": prescription.date_expiration,
            "notes": prescription.notes,
            "status": "created",
        }

        # Insert into database
        result = ordonnances_collection.insert_one(ordonnance_data)
        ordonnance_id = str(result.inserted_id)

        # Generate PDF
        pdf_path = generate_ordonnance_pdf(
            ordonnance_id=ordonnance_id,
            patient_name=prescription.patient_name,
            medicaments=prescription.medicaments,
            notes=prescription.notes,
            doctor_name=user_info.get("name", "Dr."),
        )

        # Update with PDF path
        ordonnances_collection.update_one(
            {"_id": result.inserted_id}, {"$set": {"pdf_path": pdf_path}}
        )

        # Notify about prescription creation
        rabbitmq_client.notify_prescription_created(
            prescription_id=ordonnance_id,
            doctor_id=doctor_id,
            patient_id=prescription.patient_id,
        )

        # Notify the patient
        rabbitmq_client.notify_patient_prescription(
            prescription_id=ordonnance_id,
            patient_id=prescription.patient_id,
            action="created",
        )

        return {
            "ordonnance_id": ordonnance_id,
            "message": "Prescription created successfully",
        }

    except Exception as e:
        logger_service.error(f"Error creating prescription: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post(
    "/update-prescription-status/{prescription_id}",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def update_prescription_status(
    prescription_id: str,
    status: str,
    pharmacy_id: Optional[str] = None,
    user_info: Dict = Depends(get_current_doctor),
):
    """Update prescription status and notify relevant services"""
    try:
        # Find prescription
        ordonnance = ordonnances_collection.find_one({"_id": ObjectId(prescription_id)})
        if not ordonnance:
            raise HTTPException(status_code=404, detail="Prescription not found")

        # Update status
        ordonnances_collection.update_one(
            {"_id": ObjectId(prescription_id)},
            {
                "$set": {
                    "status": status,
                    "updated_at": datetime.utcnow().isoformat(),
                    "pharmacy_id": pharmacy_id,
                }
            },
        )

        # Notify about status update
        if status == "dispensed":
            rabbitmq_client.notify_prescription_dispensed(
                prescription_id=prescription_id, pharmacy_id=pharmacy_id
            )

            # Notify the doctor
            rabbitmq_client.notify_doctor_prescription(
                prescription_id=prescription_id,
                doctor_id=ordonnance.get("medecin_id"),
                action=status,
            )

            # Notify the patient
            rabbitmq_client.notify_patient_prescription(
                prescription_id=prescription_id,
                patient_id=ordonnance.get("patient_id"),
                action=status,
            )

        return MessageResponse(message=f"Prescription status updated to {status}")

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error updating prescription status: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get(
    "/doctor-prescriptions",
    responses={500: {"model": ErrorResponse}},
)
async def get_doctor_prescriptions(user_info: Dict = Depends(get_current_doctor)):
    """Get prescriptions created by a doctor"""
    try:
        doctor_id = user_info.get("user_id")

        prescriptions = list(
            ordonnances_collection.find({"medecin_id": doctor_id}).sort(
                "date_creation", -1
            )
        )

        # Format the response
        formatted_prescriptions = []
        for prescription in prescriptions:
            formatted_prescriptions.append(
                {
                    "id": str(prescription.get("_id")),
                    "patient_id": prescription.get("patient_id"),
                    "patient_name": prescription.get("patient_name"),
                    "date_creation": prescription.get("date_creation"),
                    "date_expiration": prescription.get("date_expiration"),
                    "status": prescription.get("status"),
                    "medicaments_count": len(prescription.get("medicaments", [])),
                    "has_pdf": "pdf_path" in prescription,
                }
            )

        return {"prescriptions": formatted_prescriptions}

    except Exception as e:
        logger_service.error(f"Error retrieving doctor prescriptions: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
