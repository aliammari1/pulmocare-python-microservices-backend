import asyncio
import os

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer

from config import Config
from consumer import AppointmentConsumer
from routes.appointments import router as appointments_router
from routes.health import router as health_router
from routes.integration import router as integration_router
from routes.scheduling import router as scheduling_router
from services.logger_service import logger_service
from services.mongodb_client import MongoDBClient
from services.rabbitmq_client import RabbitMQClient

# Initialize the FastAPI application
app = FastAPI(
    title="Appointments API",
    description="API for appointment management",
    version="1.0.0",
    # Ensure consistency in handling URLs with or without trailing slashes
    redirect_slashes=False,
)

# Load configuration
config = Config()

# Security scheme
security = HTTPBearer()

# Setup CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Set to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize RabbitMQ client and consumer
rabbitmq_client = RabbitMQClient(config)
appointment_consumer = AppointmentConsumer(config)

# Initialize MongoDB client
mongodb_client = MongoDBClient(config)


@app.on_event("startup")
async def startup_event():
    """Initialize services on application startup"""
    try:
        # MongoDB connection is established during initialization
        logger_service.info("Database connection established")

        # RabbitMQ connection is established during RabbitMQClient initialization
        # No need to call connect() as it's done in the constructor
        logger_service.info("RabbitMQ connection established")

        # Start background task to consume appointment messages
        asyncio.create_task(start_appointment_consumers())

        logger_service.info("Appointments service starting up")

    except Exception as e:
        logger_service.error(f"Startup error: {str(e)}")
        raise


async def start_appointment_consumers():
    """Start RabbitMQ consumers for appointment messages"""
    try:
        # Connect and start the AppointmentConsumer
        await appointment_consumer.connect()
        await appointment_consumer.start_consuming()
        logger_service.info("Appointment message consumers started")
    except Exception as e:
        logger_service.error(f"Error starting message consumers: {str(e)}")


async def close_database_client():
    """Close the database connection properly"""
    try:
        await mongodb_client.close_async()
        return True
    except Exception as e:
        logger_service.error(f"Error closing database connection: {str(e)}")
        return False


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on application shutdown"""
    try:
        # Stop the appointment consumer
        await appointment_consumer.stop_consuming()
        logger_service.info("Appointment consumers stopped")

        # Close database connection
        await close_database_client()
        logger_service.info("Database connection closed")

        # Close RabbitMQ connection
        rabbitmq_client.close()
        logger_service.info("RabbitMQ connection closed")

        logger_service.info("Appointments service shutting down")

    except Exception as e:
        logger_service.error(f"Shutdown error: {str(e)}")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for the application"""
    logger_service.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"message": "An unexpected error occurred"},
    )


# Include routers
app.include_router(health_router, tags=["Health"])
app.include_router(
    appointments_router, prefix="/api/appointments", tags=["Appointments"]
)
app.include_router(scheduling_router, prefix="/api/scheduling", tags=["Scheduling"])
app.include_router(
    integration_router, prefix="/api/integration/appointments", tags=["Integration"]
)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8087"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, log_level="debug", reload=True)
