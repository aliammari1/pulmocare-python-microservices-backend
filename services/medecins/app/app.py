import base64
import io
import os
import random
import re
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from typing import Dict
import jwt
import pytesseract
import uvicorn
from auth.keycloak_auth import get_current_user
from bson import ObjectId
from decorator.health_check import health_check_middleware
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from models.api_models import (ErrorResponse, ForgotPasswordRequest,
                               LoginRequest, LoginResponse, MessageResponse,
                               ResetPasswordRequest, ScanVisitCardRequest,
                               ScanVisitCardResponse, SignupRequest,
                               UpdateSignatureRequest, VerifyDoctorRequest,
                               VerifyDoctorResponse, VerifyOTPRequest)
from models.doctor import Doctor, DoctorInDB, DoctorUpdate, PasswordChange
from PIL import Image
from routes.integration_routes import router as integration_router
from routes.auth_routes import router as auth_router
from routes.doctor_routes import router as doctor_router
from services.logger_service import logger_service
from services.mongodb_client import MongoDBClient
from services.rabbitmq_client import RabbitMQClient
from services.redis_client import RedisClient
from services.tracing_service import TracingService

from config import Config

# Determine environment and load corresponding .env file
env = os.getenv("ENV", "development")
dotenv_file = f".env.{env}"
if not os.path.exists(dotenv_file):
    dotenv_file = ".env"
load_dotenv(dotenv_path=dotenv_file)

# Initialize FastAPI app
app = FastAPI(
    title="MedApp Doctors Service",
    description="API for managing doctor profiles and authentication",
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
rabbitmq_client = RabbitMQClient(Config)

app.include_router(integration_router)
app.include_router(auth_router)
app.include_router(doctor_router)

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
