import os
import threading

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import Config
from services.logger_service import logger_service
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
    title="Radiologues API",
    description="API for radiologist management",
    version="1.0.0",
)

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

# Create routes (import here to avoid circular imports)
from routes.integration_routes import router as integration_router
from routes.radiologist_routes import router as radiologist_router

# Include routers
app.include_router(integration_router)
app.include_router(radiologist_router)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "UP", "service": "radiologues-service"}


if __name__ == "__main__":
    # Try to import the consumer module for background task
    try:
        from consumer import main as consumer_main

        # Start the consumer in a separate thread
        consumer_thread = threading.Thread(target=consumer_main, daemon=True)
        consumer_thread.start()
    except ImportError:
        logger_service.warning("Consumer module not found, skipping background tasks")

    # Run the FastAPI app with uvicorn
    uvicorn.run(app, host=Config.HOST, port=Config.PORT)
