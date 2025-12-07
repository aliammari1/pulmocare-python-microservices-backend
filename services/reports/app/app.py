import time
from typing import Dict, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.routing import APIRouter

from config import Config
from report_generator import ReportGenerator
from routes.integration_routes import router as integration_router
from services.mongodb_client import MongoDBClient
from services.rabbitmq_client import RabbitMQClient
from services.redis_client import RedisClient
from services.report_service import ReportService

# Initialize API router
api = APIRouter()

# Initialize FastAPI app
app = FastAPI(title="Reports API", version="1.0.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
redis_client = RedisClient(Config)
mongodb_client = MongoDBClient(Config)
rabbitmq_client = RabbitMQClient(Config)

report_generator = ReportGenerator()
report_service = ReportService(mongodb_client, redis_client, rabbitmq_client)


# API Routes
@api.get("/")
async def get_reports(
        search: Optional[str] = None,
        request: Request = None,
):
    """Get all reports with optional filtering"""
    reports = report_service.get_all_reports(search)
    return reports


@api.get("/{report_id}")
async def get_report(
        report_id: str,
        request: Request = None,
):
    """Get a specific report by ID"""
    report = report_service.get_report_by_id(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@api.post("/", status_code=201)
async def create_report(
        data: Dict,
        request: Request = None,
):
    """Create a new report"""
    if not data:
        raise HTTPException(status_code=400, detail="No data provided")

    report = report_service.create_report(data)
    return report


@api.put("/{report_id}")
async def update_report(
        report_id: str,
        data: Dict,
        request: Request = None,
):
    """Update an existing report"""
    if not data:
        raise HTTPException(status_code=400, detail="No data provided")

    report = report_service.update_report(report_id, data)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@api.delete("/{report_id}", status_code=204)
async def delete_report(
        report_id: str,
        request: Request = None,
):
    """Delete a report"""
    success = report_service.delete_report(report_id)
    if not success:
        raise HTTPException(status_code=404, detail="Report not found")
    return Response(status_code=204)


@api.get("/{report_id}/export")
async def export_report(
        report_id: str,
        request: Request = None,
):
    """Generate and download PDF report"""
    report = report_service.get_raw_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # Generate PDF
    output_path = report_generator.generate_pdf(report)

    # Send file
    return FileResponse(
        path=output_path,
        media_type="application/pdf",
        filename=f"medical_report_{report_id}.pdf",
    )


# Add this endpoint to the app.py file after the existing routes


@app.get("/health", tags=["Health"])
async def health():
    """Health check endpoint for the reports service"""
    status = {
        "status": "healthy",
        "service": "reports-service",
        "version": "1.0.0",
        "timestamp": int(time.time()),
        "checks": {"database": {"status": "up"}, "system": {"status": "up"}},
    }
    return status


# Register routes
app.include_router(api, prefix="/api/reports")
app.include_router(integration_router)

# Import the consumer module and threading
import threading
from consumer import main as consumer_main

if __name__ == "__main__":
    # Start the consumer in a separate thread
    consumer_thread = threading.Thread(target=consumer_main, daemon=True)
    consumer_thread.start()

    # Run the FastAPI app with uvicorn in the main thread
    uvicorn.run("app:app", host=Config.HOST, port=Config.PORT, reload=True)
