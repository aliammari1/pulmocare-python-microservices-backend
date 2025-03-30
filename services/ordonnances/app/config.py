import os
import urllib.parse
from datetime import timedelta

from dotenv import load_dotenv


class Config:
    env = os.getenv("ENV", "development")
    dotenv_file = f".env.{env}"
    if not os.path.exists(dotenv_file):
        dotenv_file = ".env"
    load_dotenv(dotenv_path=dotenv_file)
    """Configuration for the Medical App backend microservice"""

    # Service info
    SERVICE_NAME = "ordonnances-service"  # Updated to correct service name
    VERSION = "1.0.0"
    ENV = os.getenv("ENV")
    DEBUG = ENV == "development"
    PORT = int(os.getenv("PORT"))

    # Server settings
    HOST = os.getenv("HOST")

    # Service Discovery settings
    CONSUL_HOST = os.getenv("CONSUL_HOST")
    CONSUL_PORT = int(os.getenv("CONSUL_PORT"))
    CONSUL_TOKEN = os.getenv("CONSUL_HTTP_TOKEN")

    # MongoDB settings
    MONGODB_HOST = os.getenv("MONGODB_HOST")
    MONGODB_PORT = int(os.getenv("MONGODB_PORT"))
    MONGODB_USERNAME = os.getenv("MONGODB_USERNAME")
    MONGODB_PASSWORD = os.getenv("MONGODB_PASSWORD")
    MONGODB_DATABASE = os.getenv("MONGODB_DATABASE")
    MONGODB_POOL_SIZE = int(os.getenv("MONGODB_POOL_SIZE"))
    MONGODB_MIN_POOL_SIZE = int(os.getenv("MONGODB_MIN_POOL_SIZE"))
    MONGODB_MAX_IDLE_TIME_MS = int(os.getenv("MONGODB_MAX_IDLE_TIME_MS"))
    MONGODB_CONNECT_TIMEOUT_MS = int(os.getenv("MONGODB_CONNECT_TIMEOUT_MS"))
    MONGODB_SERVER_SELECTION_TIMEOUT_MS = int(
        os.getenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS")
    )

    # Redis settings
    REDIS_HOST = os.getenv("REDIS_HOST")
    REDIS_PORT = int(os.getenv("REDIS_PORT"))
    REDIS_DB = int(os.getenv("REDIS_DB"))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
    REDIS_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

    # RabbitMQ settings
    RABBITMQ_HOST = os.getenv("RABBITMQ_HOST")
    RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT"))
    RABBITMQ_USER = os.getenv("RABBITMQ_USER")
    RABBITMQ_PASS = os.getenv("RABBITMQ_PASS")
    RABBITMQ_VHOST = os.getenv("RABBITMQ_VHOST")

    # Logging settings
    LOG_LEVEL = os.getenv("LOG_LEVEL")
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_DIR = os.getenv("LOG_DIR")
    LOG_FILE = os.path.join(LOG_DIR, f"{SERVICE_NAME}.log")
    LOG_MAX_SIZE = int(os.getenv("LOG_MAX_SIZE"))
    LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT"))

    # Monitoring settings
    METRICS_PORT = int(os.getenv("METRICS_PORT"))
    ENABLE_METRICS = os.getenv("ENABLE_METRICS").lower() in (
        "true",
        "t",
        "1",
        "yes",
    )

    # Tracing settings
    OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    OTEL_SERVICE_NAME = SERVICE_NAME

    # Circuit Breaker settings
    CIRCUIT_BREAKER_FAILURE_THRESHOLD = int(
        os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD")
    )
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT = int(
        os.getenv("CIRCUIT_BREAKER_RECOVERY_TIMEOUT")
    )

    # Health Check settings
    HEALTH_CHECK_INTERVAL = os.getenv("HEALTH_CHECK_INTERVAL")
    HEALTH_CHECK_TIMEOUT = os.getenv("HEALTH_CHECK_TIMEOUT")
    HEALTH_CHECK_DEREGISTER_TIMEOUT = os.getenv("HEALTH_CHECK_DEREGISTER_TIMEOUT")

    # Cache settings
    CACHE_TTL = int(os.getenv("CACHE_TTL"))
    CACHE_MAX_SIZE = int(os.getenv("CACHE_MAX_SIZE"))
    CACHE_TYPE = "redis"
    CACHE_REDIS_URL = REDIS_URL
    CACHE_DEFAULT_TIMEOUT = CACHE_TTL

    # Rate limiting
    RATE_LIMIT_STORAGE_URL = os.getenv(
        "RATE_LIMIT_STORAGE_URL",
        f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/0",
    )
    RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT")

    # Application specific configuration
    PDF_EXPORT_PATH = os.getenv("PDF_EXPORT_PATH")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    REQUEST_TIMEOUT = 30  # seconds

    # Session configuration
    SESSION_TYPE = "redis"
    SESSION_REDIS = REDIS_URL
    SESSION_USE_SIGNER = True
    PERMANENT_SESSION_LIFETIME = timedelta(days=1)

    # Security configuration
    SECRET_KEY = os.getenv("SECRET_KEY")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)

    @classmethod
    def get_mongodb_uri(cls):
        """Get MongoDB connection URI with proper handling of special characters in password"""
        username = urllib.parse.quote_plus(cls.MONGODB_USERNAME)
        password = urllib.parse.quote_plus(cls.MONGODB_PASSWORD)
        return (
            f"mongodb://{username}:{password}@" f"{cls.MONGODB_HOST}:{cls.MONGODB_PORT}"
        )

    @classmethod
    def get_mongodb_validation_schema(cls):
        """Get MongoDB validation schema for reports collection"""
        return {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["title", "content", "created_at", "updated_at"],
                "properties": {
                    "title": {"bsonType": "string"},
                    "content": {"bsonType": "string"},
                    "patient_id": {"bsonType": "string"},
                    "doctor_id": {"bsonType": "string"},
                    "analysis": {
                        "bsonType": ["object", "null"],
                        "properties": {
                            "findings": {
                                "bsonType": "array",
                                "items": {
                                    "bsonType": "object",
                                    "required": [
                                        "condition",
                                        "severity",
                                        "description",
                                    ],
                                    "properties": {
                                        "condition": {"bsonType": "string"},
                                        "severity": {
                                            "enum": ["mild", "moderate", "severe"]
                                        },
                                        "description": {"bsonType": "string"},
                                        "confidence_score": {"bsonType": "double"},
                                        "probability": {"bsonType": "double"},
                                    },
                                },
                            },
                            "technical_details": {
                                "bsonType": "object",
                                "properties": {
                                    "quality_metrics": {"bsonType": "object"},
                                    "image_stats": {"bsonType": "object"},
                                },
                            },
                        },
                    },
                    "annotations": {
                        "bsonType": "array",
                        "items": {
                            "bsonType": "object",
                            "required": ["type", "timestamp"],
                            "properties": {
                                "type": {"enum": ["drawing", "text"]},
                                "points": {
                                    "bsonType": "array",
                                    "items": {
                                        "bsonType": "object",
                                        "required": ["x", "y", "color", "strokeWidth"],
                                        "properties": {
                                            "x": {"bsonType": "double"},
                                            "y": {"bsonType": "double"},
                                            "color": {"bsonType": "int"},
                                            "strokeWidth": {"bsonType": "double"},
                                        },
                                    },
                                },
                                "text": {"bsonType": "string"},
                                "timestamp": {"bsonType": "string"},
                            },
                        },
                    },
                    "created_at": {"bsonType": "date"},
                    "updated_at": {"bsonType": "date"},
                    "tags": {"bsonType": "array", "items": {"bsonType": "string"}},
                },
            }
        }



    @classmethod
    def validate(cls):
        """Validate required configuration settings"""
        required_settings = [
            "MONGODB_USERNAME",
            "MONGODB_PASSWORD",
            "MONGODB_HOST",
            "CONSUL_HOST",
            "RABBITMQ_HOST",
        ]

        missing = [
            setting for setting in required_settings if not getattr(cls, setting, None)
        ]

        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")
