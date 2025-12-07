import logging
import os
import socket
from logging.handlers import RotatingFileHandler

from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

from config import Config


class LoggerService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggerService, cls).__new__(cls)

            # Create logs directory if it doesn't exist
            os.makedirs(Config.LOG_DIR, exist_ok=True)

            # Ensure the log file path exists
            log_file_dir = os.path.dirname(Config.LOG_FILE)
            if log_file_dir:
                os.makedirs(log_file_dir, exist_ok=True)

            # Initialize logger
            cls._instance.logger = logging.getLogger(Config.SERVICE_NAME)
            cls._instance.logger.setLevel(Config.LOG_LEVEL)

            # Create formatters and handlers
            formatter = logging.Formatter(Config.LOG_FORMAT)

            try:
                # File Handler
                file_handler = RotatingFileHandler(
                    Config.LOG_FILE,
                    maxBytes=Config.LOG_MAX_SIZE,
                    backupCount=Config.LOG_BACKUP_COUNT,
                )
                file_handler.setFormatter(formatter)
                file_handler.setLevel(Config.LOG_LEVEL)
                cls._instance.logger.addHandler(file_handler)
            except Exception as e:
                print(
                    f"Failed to create file handler: {str(e)}. Using console logging only."
                )

            # Console Handler
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            console_handler.setLevel(Config.LOG_LEVEL)

            # Add handlers to logger
            cls._instance.logger.addHandler(console_handler)

            # Setup OpenTelemetry logging
            cls._instance._setup_otel_logging()

            # Setup FastAPI/uvicorn logging capture
            cls._instance._setup_fastapi_logging()

        return cls._instance

    def _setup_otel_logging(self):
        """Set up OpenTelemetry logging"""
        try:
            # Create a Resource to identify the service
            resource = Resource.create(
                {
                    "service.name": Config.SERVICE_NAME,
                    "service.instance.id": socket.gethostname(),
                }
            )

            # Create the LoggerProvider with the resource
            logger_provider = LoggerProvider(resource=resource)

            # Set as the global logger provider
            set_logger_provider(logger_provider)

            # Create the exporter and processor
            exporter = OTLPLogExporter(
                endpoint=f"http://{'localhost' if Config.ENV == 'development' else 'otel-collector'}:4317",
                insecure=True,
            )
            logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))

            # Create and add the OpenTelemetry handler
            otel_handler = LoggingHandler(
                level=logging.NOTSET, logger_provider=logger_provider
            )
            self.logger.addHandler(otel_handler)

            self.logger.info(
                f"OpenTelemetry logging initialized for {Config.SERVICE_NAME}"
            )
        except Exception as e:
            # Log to standard handlers if OTEL setup fails
            self.logger.error(f"Failed to initialize OpenTelemetry logging: {str(e)}")

    def _setup_fastapi_logging(self):
        """Configure FastAPI/uvicorn logging to use our handlers"""
        try:
            # Get the formatters and handlers from our logger
            handlers = self.logger.handlers

            # Configure uvicorn loggers
            uvicorn_loggers = [
                'uvicorn',
                'uvicorn.error',
                'uvicorn.access',
                'fastapi'
            ]

            for logger_name in uvicorn_loggers:
                logger = logging.getLogger(logger_name)
                logger.handlers.clear()  # Remove existing handlers
                logger.propagate = False  # Prevent duplicate logs
                logger.setLevel(Config.LOG_LEVEL)

                # Add our handlers to uvicorn loggers
                for handler in handlers:
                    logger.addHandler(handler)

            # Also configure root logger to catch any other logs
            root_logger = logging.getLogger()
            root_logger.setLevel(Config.LOG_LEVEL)

            # Add our handlers to root logger if not already present
            for handler in handlers:
                if handler not in root_logger.handlers:
                    root_logger.addHandler(handler)

            self.logger.info("FastAPI/uvicorn logging capture configured")

        except Exception as e:
            self.logger.error(f"Failed to setup FastAPI logging capture: {str(e)}")

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = LoggerService()
        return cls._instance

    def info(self, message):
        self.logger.info(message)

    def warning(self, message):
        self.logger.warning(message)

    def error(self, message):
        self.logger.error(message)

    def debug(self, message):
        self.logger.debug(message)

    def exception(self, message):
        self.logger.exception(message)


# Singleton instance
logger_service = LoggerService.get_instance()
