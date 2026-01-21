import json
import logging
import traceback
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import Config


class JsonFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings after parsing the log record.
    """

    def format(self, record):
        """
        Format the log record as JSON.
        """
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "service": "medfiles-service",
        }

        # Add exception info if available
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info),
            }

        # Add extra attributes from record
        for key, value in record.__dict__.items():
            if key not in {
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "id",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
            }:
                log_data[key] = value

        return json.dumps(log_data)


class LoggerService:
    """
    Singleton Logger Service for the MedFiles Service
    Provides logging to console and file with OpenTelemetry integration
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggerService, cls).__new__(cls)
            cls._instance.logger = logging.getLogger("medfiles-service")
            cls._instance.logger.setLevel(Config.LOG_LEVEL)
            cls._instance.logger.propagate = False

            # Clear any existing handlers to avoid duplication
            cls._instance.logger.handlers = []

            # Setup formatter based on configuration
            if Config.LOG_FORMAT.lower() == "json":
                formatter = JsonFormatter()
            else:
                formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

            try:
                # Create log directory if it doesn't exist
                Path(Config.LOG_DIR).mkdir(parents=True, exist_ok=True)

                # File Handler with rotation
                file_handler = RotatingFileHandler(
                    Config.LOG_FILE,
                    maxBytes=Config.LOG_MAX_SIZE,
                    backupCount=Config.LOG_BACKUP_COUNT,
                )
                file_handler.setFormatter(formatter)
                file_handler.setLevel(Config.LOG_LEVEL)
                cls._instance.logger.addHandler(file_handler)

            except Exception as e:
                print(f"Failed to create file handler: {e!s}. Using console logging only.")

            # Console Handler
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            console_handler.setLevel(Config.LOG_LEVEL)

            # Add handlers to logger
            cls._instance.logger.addHandler(console_handler)

            # Setup OpenTelemetry logging
            cls._instance._setup_otel_logging()

        return cls._instance

    def _setup_otel_logging(self):
        """
        Set up OpenTelemetry logging instrumentation
        """
        try:
            from opentelemetry.instrumentation.logging import LoggingInstrumentor

            LoggingInstrumentor().instrument(
                set_logging_format=True,
                log_level=Config.LOG_LEVEL,
            )
        except ImportError:
            self.logger.warning("OpenTelemetry logging instrumentation not available")
        except Exception as e:
            self.logger.warning(f"Failed to set up OpenTelemetry logging: {e!s}")

    def debug(self, message, **kwargs):
        """Log a debug message"""
        self.logger.debug(message, extra=kwargs)

    def info(self, message, **kwargs):
        """Log an info message"""
        self.logger.info(message, extra=kwargs)

    def warning(self, message, **kwargs):
        """Log a warning message"""
        self.logger.warning(message, extra=kwargs)

    def error(self, message, exc_info=None, **kwargs):
        """Log an error message"""
        self.logger.error(message, exc_info=exc_info, extra=kwargs)

    def critical(self, message, exc_info=None, **kwargs):
        """Log a critical message"""
        self.logger.critical(message, exc_info=exc_info, extra=kwargs)

    def exception(self, message, **kwargs):
        """Log an exception message"""
        self.logger.exception(message, extra=kwargs)
