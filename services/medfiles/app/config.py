import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file if it exists
env_file = Path(".env")
if env_file.exists():
    load_dotenv(env_file)


class Config:
    """Configuration for the MedFiles Service"""

    # Service info
    SERVICE_NAME = "medfiles-service"
    VERSION = "1.0.0"
    ENV = os.getenv("ENV", "development")
    DEBUG = ENV == "development"
    PORT = int(os.getenv("PORT", 8088))

    # Server settings
    HOST = os.getenv("HOST", "0.0.0.0")

    # MinIO settings
    MINIO_HOST = os.getenv("MINIO_HOST", "minio")
    MINIO_PORT = os.getenv("MINIO_PORT", 9000)
    MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    MINIO_REGION = os.getenv("MINIO_REGION", "us-east-1")
    MINIO_SECURE = os.getenv("MINIO_SECURE", "false")

    # Service Discovery settings
    CONSUL_HOST = os.getenv("CONSUL_HOST", "consul")
    CONSUL_PORT = int(os.getenv("CONSUL_PORT", 8500))
    CONSUL_TOKEN = os.getenv("CONSUL_HTTP_TOKEN")

    # Authentication settings
    AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8086")

    # Logging settings
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT = os.getenv("LOG_FORMAT", "json")
    LOG_DIR = os.getenv("LOG_DIR", "./logs")
    LOG_FILE = os.path.join(LOG_DIR, f"{SERVICE_NAME}.log")
    LOG_MAX_SIZE = int(os.getenv("LOG_MAX_SIZE", 10485760))  # 10MB
    LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", 5))

    # OpenTelemetry settings
    OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    OTEL_SERVICE_NAME = SERVICE_NAME

    # Maximum file size for uploads (100MB)
    MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 104857600))
