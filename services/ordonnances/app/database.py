import logging
import os

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

logger = logging.getLogger(__name__)


def get_database():
    try:
        client = MongoClient("mongodb://admin:admin@localhost:27017/")
        # Test the connection
        client.admin.command("ping")
        logger.info("Successfully connected to MongoDB")
        return client["medapp"]
    except ConnectionFailure as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error with MongoDB: {e}")
        raise


db = get_database()
