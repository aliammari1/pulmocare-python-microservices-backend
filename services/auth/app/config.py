import os

from dotenv import load_dotenv


class Config:
    env = os.getenv("ENV", "development")
    dotenv_file = f".env.{env}"
    if not os.path.exists(dotenv_file):
        dotenv_file = ".env"
    load_dotenv(dotenv_path=dotenv_file)
    """Configuration for the MedApp Authentication Service"""

    # Service info
    SERVICE_NAME = "auth-service"
    VERSION = "1.0.0"
    ENV = os.getenv("ENV")
    DEBUG = ENV == "development"
    PORT = int(os.getenv("PORT", 8086))

    # Server settings
    HOST = os.getenv("HOST", "0.0.0.0")

    # Service Discovery settings
    CONSUL_HOST = os.getenv("CONSUL_HOST", "localhost")
    CONSUL_PORT = int(os.getenv("CONSUL_PORT", 8500))
    CONSUL_TOKEN = os.getenv("CONSUL_HTTP_TOKEN", "")

    # MongoDB settings
    MONGODB_HOST = os.getenv("MONGODB_HOST", "localhost")
    MONGODB_PORT = int(os.getenv("MONGODB_PORT", 27017))
    MONGODB_USERNAME = os.getenv("MONGODB_USERNAME", "admin")
    MONGODB_PASSWORD = os.getenv("MONGODB_PASSWORD", "admin")
    MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "pulmocare")
    MONGODB_POOL_SIZE = int(os.getenv("MONGODB_POOL_SIZE", 50))
    MONGODB_MIN_POOL_SIZE = int(os.getenv("MONGODB_MIN_POOL_SIZE", 10))
    MONGODB_MAX_IDLE_TIME_MS = int(os.getenv("MONGODB_MAX_IDLE_TIME_MS", 60000))
    MONGODB_CONNECT_TIMEOUT_MS = int(os.getenv("MONGODB_CONNECT_TIMEOUT_MS", 5000))
    MONGODB_SERVER_SELECTION_TIMEOUT_MS = int(os.getenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", 5000))

    # Redis settings
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB = int(os.getenv("REDIS_DB", 0))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "redispass")

    # RabbitMQ settings
    RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
    RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", 5672))
    RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
    RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
    RABBITMQ_VHOST = os.getenv("RABBITMQ_VHOST", "/")

    # Logging settings
    LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG")
    LOG_DIR = os.getenv("LOG_DIR", "logs")
    LOG_MAX_SIZE = int(os.getenv("LOG_MAX_SIZE", 10485760))
    LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", 5))

    # Monitoring settings
    METRICS_PORT = int(os.getenv("METRICS_PORT", 9096))
    ENABLE_METRICS = os.getenv("ENABLE_METRICS", "True").lower() == "true"

    # Tracing settings
    OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    OTEL_DISABLE_ON_ERROR = os.getenv("OTEL_DISABLE_ON_ERROR", "True").lower() == "true"

    # Keycloak settings
    KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8090")
    KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "pulmocare")
    KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "pulmocare-api")
    KEYCLOAK_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "pulmocare-secret")
    KEYCLOAK_ADMIN_USERNAME = os.getenv("KEYCLOAK_ADMIN_USERNAME", "admin")
    KEYCLOAK_ADMIN_PASSWORD = os.getenv("KEYCLOAK_ADMIN_PASSWORD", "admin")

    # JWT settings
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret-key-change-in-production")
    JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", 3600))  # 1 hour
    JWT_REFRESH_TOKEN_EXPIRES = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES", 2592000))  # 30 days

    # Default redirect URL after login (if applicable)
    DEFAULT_REDIRECT_URL = os.getenv("DEFAULT_REDIRECT_URL", "http://localhost:3000")

    # CORS settings
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
