import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer

from config import Config
from routes.integration_routes import router as integration_router
from routes.patients_routes import router as patients_router
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
    title="Patients API",
    description="API for patient management",
    version="1.0.0",
)

# Security scheme
security = HTTPBearer()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
redis_client = RedisClient(Config)
rabbitmq_client = RabbitMQClient(Config)
tracing_service = TracingService(Config)

# Create authentication and routes
app.include_router(integration_router)
app.include_router(patients_router)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "UP", "service": "patients-service"}


if __name__ == "__main__":
    uvicorn.run(app, host=Config.HOST, port=Config.PORT)
