import base64
import os
from datetime import datetime
from typing import Dict, Optional

import uvicorn
from bson import ObjectId
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pymongo import DESCENDING

from config import Config
from decorator.health_check import health_check_middleware
from models.api_models import ErrorResponse, MessageResponse
from models.ordonnance import (
    Ordonnance,
    OrdonnanceCreate,
    OrdonnanceInDB,
    OrdonnanceList,
    OrdonnanceUpdate,
)
from routes.integration_routes import get_current_doctor, router as integration_router
from services.logger_service import logger_service
from services.mongodb_client import MongoDBClient
from services.rabbitmq_client import RabbitMQClient
from services.redis_client import RedisClient
from services.tracing_service import TracingService

# Determine environment and load corresponding .env file
env = os.getenv("ENV", "development")
dotenv_file = f".env.{env}"
if not os.path.exists(dotenv_file):
    dotenv_file = ".env"
load_dotenv(dotenv_path=dotenv_file)

# Initialize FastAPI app
app = FastAPI(
    title="MedApp Prescriptions Service",
    description="API for managing medical prescriptions",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update with specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Apply health check middleware
app = health_check_middleware(Config)(app)

# Initialize services
tracing_service = TracingService(app)
redis_client = RedisClient(Config)
mongodb_client = MongoDBClient(Config)
rabbitmq_client = RabbitMQClient(Config)

# MongoDB collections
ordonnances_collection = mongodb_client.db.ordonnances


@app.post(
    "/api/ordonnances",
    response_model=OrdonnanceInDB,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def create_ordonnance(
        ordonnance_data: OrdonnanceCreate, user_info: Dict = Depends(get_current_doctor)
):
    try:
        doctor_id = user_info.get("user_id")

        # Create new ordonnance document
        ordonnance = Ordonnance(
            doctor_id=doctor_id,
            patient_id=ordonnance_data.patient_id,
            patient_name=ordonnance_data.patient_name,
            doctor_name=ordonnance_data.doctor_name,
            medications=ordonnance_data.medications,
            instructions=ordonnance_data.instructions,
            diagnosis=ordonnance_data.diagnosis,
            date=datetime.now(),
            signature=ordonnance_data.signature,
        )

        # Save to database
        result = ordonnances_collection.insert_one(ordonnance.to_dict())

        # Get the created ordonnance
        created_ordonnance = ordonnances_collection.find_one(
            {"_id": result.inserted_id}
        )

        # Convert to Pydantic model
        return Ordonnance.from_dict(created_ordonnance).to_pydantic()

    except Exception as e:
        logger_service.error(f"Error creating prescription: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create prescription: {str(e)}"
        )


@app.get(
    "/api/ordonnances",
    response_model=OrdonnanceList,
    responses={500: {"model": ErrorResponse}},
)
async def get_ordonnances(
        patient_id: Optional[str] = None,
        doctor_id: Optional[str] = None,
        limit: int = 100,
        skip: int = 0,
):
    try:
        # Build query based on parameters
        query = {}
        if patient_id:
            query["patient_id"] = patient_id
        if doctor_id:
            query["doctor_id"] = doctor_id

        # Get count for pagination
        total = ordonnances_collection.count_documents(query)

        # Get ordonnances with pagination
        cursor = (
            ordonnances_collection.find(query)
            .sort("date", DESCENDING)
            .skip(skip)
            .limit(limit)
        )

        # Convert to list of OrdonnanceInDB models
        ordonnances = [Ordonnance.from_dict(ord).to_pydantic() for ord in cursor]

        return OrdonnanceList(
            items=ordonnances,
            total=total,
            page=skip // limit + 1 if limit > 0 else 1,
            pages=(total + limit - 1) // limit if limit > 0 else 1,
        )

    except Exception as e:
        logger_service.error(f"Error retrieving prescriptions: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve prescriptions: {str(e)}"
        )


@app.get(
    "/api/ordonnances/{ordonnance_id}",
    response_model=OrdonnanceInDB,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_ordonnance(ordonnance_id: str):
    try:
        # Validate ID format
        if not ObjectId.is_valid(ordonnance_id):
            raise HTTPException(
                status_code=400, detail="Invalid prescription ID format"
            )

        # Find ordonnance by ID
        ordonnance_data = ordonnances_collection.find_one(
            {"_id": ObjectId(ordonnance_id)}
        )

        if not ordonnance_data:
            raise HTTPException(status_code=404, detail="Prescription not found")

        # Convert to Pydantic model
        return Ordonnance.from_dict(ordonnance_data).to_pydantic()

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error retrieving prescription: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve prescription: {str(e)}"
        )


@app.put(
    "/api/ordonnances/{ordonnance_id}",
    response_model=OrdonnanceInDB,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def update_ordonnance(
        ordonnance_id: str,
        update_data: OrdonnanceUpdate,
        user_info: Dict = Depends(get_current_doctor),
):
    try:
        # Validate ID format
        if not ObjectId.is_valid(ordonnance_id):
            raise HTTPException(
                status_code=400, detail="Invalid prescription ID format"
            )

        # Find ordonnance by ID
        ordonnance_data = ordonnances_collection.find_one(
            {"_id": ObjectId(ordonnance_id)}
        )

        if not ordonnance_data:
            raise HTTPException(status_code=404, detail="Prescription not found")

        # Check if the doctor is the owner
        if ordonnance_data.get("doctor_id") != user_info.get("user_id"):
            raise HTTPException(
                status_code=403, detail="You can only update your own prescriptions"
            )

        # Prepare update data
        update_fields = {}
        for field, value in update_data.dict(exclude_unset=True).items():
            if value is not None:
                update_fields[field] = value

        # Update the document
        ordonnances_collection.update_one(
            {"_id": ObjectId(ordonnance_id)}, {"$set": update_fields}
        )

        # Get updated ordonnance
        updated_ordonnance = ordonnances_collection.find_one(
            {"_id": ObjectId(ordonnance_id)}
        )

        # Convert to Pydantic model
        return Ordonnance.from_dict(updated_ordonnance).to_pydantic()

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error updating prescription: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to update prescription: {str(e)}"
        )


@app.delete(
    "/api/ordonnances/{ordonnance_id}",
    response_model=MessageResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def delete_ordonnance(
        ordonnance_id: str, user_info: Dict = Depends(get_current_doctor)
):
    try:
        # Validate ID format
        if not ObjectId.is_valid(ordonnance_id):
            raise HTTPException(
                status_code=400, detail="Invalid prescription ID format"
            )

        # Find ordonnance by ID
        ordonnance_data = ordonnances_collection.find_one(
            {"_id": ObjectId(ordonnance_id)}
        )

        if not ordonnance_data:
            raise HTTPException(status_code=404, detail="Prescription not found")

        # Check if the doctor is the owner
        if ordonnance_data.get("doctor_id") != user_info.get("user_id"):
            raise HTTPException(
                status_code=403, detail="You can only delete your own prescriptions"
            )

        # Delete the document
        result = ordonnances_collection.delete_one({"_id": ObjectId(ordonnance_id)})

        if result.deleted_count == 0:
            raise HTTPException(status_code=500, detail="Failed to delete prescription")

        return {"message": "Prescription deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error deleting prescription: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to delete prescription: {str(e)}"
        )


@app.get(
    "/api/generate-pdf/{ordonnance_id}",
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def generate_pdf(ordonnance_id: str):
    try:
        # Import FPDF at function level to avoid global import issues
        from fpdf import FPDF

        # Validate ID format
        if not ObjectId.is_valid(ordonnance_id):
            raise HTTPException(
                status_code=400, detail="Invalid prescription ID format"
            )

        # Find ordonnance by ID
        ordonnance_data = ordonnances_collection.find_one(
            {"_id": ObjectId(ordonnance_id)}
        )

        if not ordonnance_data:
            raise HTTPException(status_code=404, detail="Prescription not found")

        # Create PDF
        pdf_path = f"prescription_{ordonnance_id}.pdf"

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)

        # Add header
        pdf.cell(200, 10, txt="Medical Prescription", ln=True, align="C")
        pdf.line(10, 20, 200, 20)
        pdf.ln(5)

        # Doctor and patient info
        pdf.cell(
            200,
            10,
            txt=f"Doctor: {ordonnance_data.get('doctor_name', 'N/A')}",
            ln=True,
            align="L",
        )
        pdf.cell(
            200,
            10,
            txt=f"Patient: {ordonnance_data.get('patient_name', 'N/A')}",
            ln=True,
            align="L",
        )
        pdf.cell(
            200,
            10,
            txt=f"Date: {ordonnance_data.get('date').strftime('%Y-%m-%d %H:%M')}",
            ln=True,
            align="L",
        )
        pdf.ln(5)

        # Diagnosis
        pdf.set_font("Arial", "B", 12)
        pdf.cell(200, 10, txt="Diagnosis:", ln=True, align="L")
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(190, 10, txt=ordonnance_data.get("diagnosis", "N/A"))
        pdf.ln(5)

        # Medications
        pdf.set_font("Arial", "B", 12)
        pdf.cell(200, 10, txt="Medications:", ln=True, align="L")
        pdf.set_font("Arial", size=12)

        for medication in ordonnance_data.get("medications", []):
            pdf.multi_cell(
                190,
                10,
                txt=f"• {medication.get('name', 'N/A')} - {medication.get('dosage', 'N/A')} - {medication.get('frequency', 'N/A')}",
            )

        pdf.ln(5)

        # Instructions
        pdf.set_font("Arial", "B", 12)
        pdf.cell(200, 10, txt="Instructions:", ln=True, align="L")
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(190, 10, txt=ordonnance_data.get("instructions", "N/A"))

        # Add signature if available
        if "signature" in ordonnance_data and ordonnance_data["signature"]:
            pdf.ln(10)
            pdf.cell(200, 10, txt="Doctor's Signature:", ln=True, align="L")

            # Convert base64 signature to image and add to PDF
            try:
                signature_data = base64.b64decode(
                    ordonnance_data["signature"].split(",")[1]
                )
                temp_sig_file = f"temp_signature_{ordonnance_id}.png"

                with open(temp_sig_file, "wb") as f:
                    f.write(signature_data)

                pdf.image(temp_sig_file, x=10, y=None, w=50)

                # Clean up temp file
                if os.path.exists(temp_sig_file):
                    os.remove(temp_sig_file)
            except Exception as sig_error:
                logger_service.error(f"Error adding signature to PDF: {str(sig_error)}")

        # Save PDF
        pdf.output(pdf_path)

        # Return PDF as download
        return FileResponse(
            path=pdf_path,
            filename=f"prescription_{ordonnance_id}.pdf",
            media_type="application/pdf",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger_service.error(f"Error generating PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {str(e)}")


# Include the integration router
app.include_router(integration_router)

# Import the consumer module and threading
import threading
from consumer import main as consumer_main

if __name__ == "__main__":
    # Start the consumer in a separate thread
    consumer_thread = threading.Thread(target=consumer_main, daemon=True)
    consumer_thread.start()

    # Run the FastAPI app with uvicorn in the main thread
    uvicorn.run(
        "app:app", host=Config.HOST, port=Config.PORT, reload=True, log_level="debug"
    )
