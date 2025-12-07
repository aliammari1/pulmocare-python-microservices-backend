import os
import threading

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import Config
from decorator.health_check import health_check_middleware
from routes.doctor_routes import router as doctor_router
from routes.integration_routes import router as integration_router
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
    title="MedApp Doctors Service",
    description="API for managing doctor profiles and authentication",
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

# Apply health check middleware
app = health_check_middleware(Config)(app)

# Initialize services
tracing_service = TracingService(app)
redis_client = RedisClient(Config)
rabbitmq_client = RabbitMQClient(Config)

app.include_router(integration_router)
app.include_router(doctor_router)

# Import the consumer module and threading
from consumer import main as consumer_main

if __name__ == "__main__":
    # Start the consumer in a separate thread
    consumer_thread = threading.Thread(target=consumer_main, daemon=True)
    consumer_thread.start()

    # Run the FastAPI app with uvicorn in the main thread
    uvicorn.run("app:app", host="0.0.0.0", port=8081, reload=True, log_level="debug")
