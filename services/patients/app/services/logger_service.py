import logging
import os
from logging.handlers import RotatingFileHandler

from config import Config


class LoggerService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggerService, cls).__new__(cls)

            # Create logs directory if it doesn't exist
            os.makedirs(Config.LOG_DIR, exist_ok=True)

            # Initialize logger
            cls._instance.logger = logging.getLogger(Config.SERVICE_NAME)
            cls._instance.logger.setLevel(Config.LOG_LEVEL)

            # Create formatters and handlers
            formatter = logging.Formatter(Config.LOG_FORMAT)

            # File Handler
            file_handler = RotatingFileHandler(
                Config.LOG_FILE,
                maxBytes=Config.LOG_MAX_SIZE,
                backupCount=Config.LOG_BACKUP_COUNT,
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(Config.LOG_LEVEL)

            # Console Handler
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            console_handler.setLevel(Config.LOG_LEVEL)

            # Add handlers to logger
            cls._instance.logger.addHandler(file_handler)
            cls._instance.logger.addHandler(console_handler)

        return cls._instance

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


logger_service = LoggerService.get_instance()
