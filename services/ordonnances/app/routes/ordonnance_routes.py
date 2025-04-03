import datetime
import os
from typing import Any, Dict, List, Optional

import bson
from bson import ObjectId
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from services.mongodb_client import MongoDBClient
from services.pdf_service import generate_ordonnance_pdf

from config import Config


# Models
class Medicament(BaseModel):
    nom: str
    dosage: str
    duree: str
    instructions: Optional[str] = None


class OrdonnanceCreate(BaseModel):
    patient_id: str
    medecin_id: str
    medicaments: List[Dict[str, str]]
    clinique: Optional[str] = ""
    specialite: Optional[str] = ""


class OrdonnanceResponse(BaseModel):
    id: str
    patient_id: str
    medecin_id: str
    medicaments: List[Dict[str, str]]
    clinique: Optional[str] = ""
    specialite: Optional[str] = ""
    date: str
    has_pdf: Optional[bool] = False
    pdf_filename: Optional[str] = None


class StatusMessage(BaseModel):
    status: str
    message: str


class VerifyResponse(BaseModel):
    status: str
    is_valid: bool
    ordonnance_id: str


# Initialize router and database
ordonnance_router = APIRouter(tags=["ordonnances"])
db = MongoDBClient(Config).db


# Endpoints
@ordonnance_router.post(
    "", response_model=Dict[str, str], status_code=status.HTTP_201_CREATED
)
async def create_ordonnance(data: OrdonnanceCreate):
    try:
        # Create the ordonnance
        ordonnance = {
            "patient_id": data.patient_id,
            "medecin_id": data.medecin_id,
            "medicaments": data.medicaments,
            "clinique": data.clinique,
            "specialite": data.specialite,
            "date": datetime.datetime.now().isoformat(),
        }

        # Save to MongoDB
        result = db.ordonnances.insert_one(ordonnance)

        return {
            "id": str(result.inserted_id),
            "message": "Ordonnance créée avec succès",
        }
    except Exception as e:
        print("Error:", str(e))  # Debug print
        raise HTTPException(status_code=500, detail=str(e))


@ordonnance_router.get("/", response_model=List[Dict[str, Any]])
async def get_ordonnances():
    ordonnances = list(db.ordonnances.find())
    for ord in ordonnances:
        ord["_id"] = str(ord["_id"])
    return ordonnances


@ordonnance_router.get(
    "/medecin/{medecin_id}/ordonnances", response_model=List[Dict[str, Any]]
)
async def get_medecin_ordonnances(medecin_id: str):
    try:
        ordonnances = list(db.ordonnances.find({"medecin_id": medecin_id}))
        for ord in ordonnances:
            ord["_id"] = str(ord["_id"])
            if isinstance(ord.get("date"), datetime.datetime):
                ord["date"] = ord["date"].isoformat()

            # Check if PDF exists for this ordonnance
            pdf_doc = db.pdf_files.find_one({"ordonnance_id": str(ord["_id"])})
            ord["has_pdf"] = pdf_doc is not None
            if pdf_doc:
                ord["pdf_filename"] = pdf_doc["filename"]

        return ordonnances
    except Exception as e:
        print(f"Erreur lors de la récupération des ordonnances: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@ordonnance_router.post("/ordonnances/{id}/pdf", response_model=Dict[str, str])
async def save_ordonnance_pdf(id: str, pdf: UploadFile = File(...)):
    try:
        ordonnance = db.ordonnances.find_one({"_id": ObjectId(id)})
        if not ordonnance:
            raise HTTPException(status_code=404, detail="Ordonnance non trouvée")

        pdf_bytes = await pdf.read()
        filename = pdf_service.save_pdf(
            ordonnance["medecin_id"], pdf_bytes, str(ordonnance["_id"])
        )

        return {"message": "PDF sauvegardé", "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@ordonnance_router.get("/ordonnance/{id}", response_model=Dict[str, Any])
async def get_ordonnance(id: str):
    try:
        # Validate ObjectId format
        try:
            obj_id = ObjectId(id)
        except bson.errors.InvalidId:
            raise HTTPException(status_code=400, detail="Invalid ordonnance ID format")

        ordonnance = db.ordonnances.find_one({"_id": obj_id})
        if not ordonnance:
            raise HTTPException(status_code=404, detail="Ordonnance not found")

        ordonnance["_id"] = str(ordonnance["_id"])
        pdf_info = db.pdf_files.find_one({"ordonnance_id": str(ordonnance["_id"])})
        ordonnance["has_pdf"] = pdf_info is not None
        if pdf_info:
            ordonnance["pdf_filename"] = pdf_info["filename"]
        return ordonnance
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching ordonnance {id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Erreur lors de la récupération de l'ordonnance"
        )


@ordonnance_router.get("/{ordonnance_id}/pdf")
async def get_ordonnance_pdf(ordonnance_id: str):
    try:
        ordonnance = db.ordonnances.find_one({"_id": ObjectId(ordonnance_id)})
        if not ordonnance:
            raise HTTPException(status_code=404, detail="Ordonnance non trouvée")

        # Look first for existing PDF
        pdf_doc = db.pdf_files.find_one({"ordonnance_id": ordonnance_id})
        if pdf_doc and os.path.exists(pdf_doc["path"]):
            return FileResponse(pdf_doc["path"], media_type="application/pdf")

        # If no existing PDF, generate a new one
        pdf_path = generate_ordonnance_pdf(ordonnance)

        # Save PDF reference
        db.pdf_files.insert_one(
            {
                "ordonnance_id": ordonnance_id,
                "filename": f"ordonnance_{ordonnance_id}.pdf",
                "path": pdf_path,
                "created_at": datetime.datetime.now(),
            }
        )

        return FileResponse(pdf_path, media_type="application/pdf")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@ordonnance_router.get("/ordonnances/{id}/verify", response_model=VerifyResponse)
async def verify_ordonnance(id: str):
    try:
        ordonnance = db.ordonnances.find_one({"_id": ObjectId(id)})
        if not ordonnance:
            raise HTTPException(status_code=404, detail="Ordonnance non trouvée")

        # Basic verification
        is_valid = (
            ordonnance.get("patient_id")
            and ordonnance.get("medecin_id")
            and ordonnance.get("medicaments")
        )

        return {
            "status": "success",
            "is_valid": is_valid,
            "ordonnance_id": str(ordonnance["_id"]),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@ordonnance_router.get("/test", response_model=StatusMessage)
async def test_connection():
    return {"status": "success", "message": "API is working"}
