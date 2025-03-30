import time
from datetime import datetime

from bson import ObjectId
from pymongo import MongoClient
from services.logger_service import logger_service


class MongoDBClient:
    """MongoDB client service for database operations"""

    def __init__(self, config):
        self.config = config

        self.client = None
        self.db = None
        self.radiologues_collection = None
        self.init_connection()

    def init_connection(self):
        """Initialize MongoDB connection with schema validation"""
        max_retries = 5
        retry_delay = 1

        for attempt in range(max_retries):
            try:
                self.client = MongoClient(
                    f"mongodb://admin:admin@{self.config.MONGODB_HOST}:27017/"
                )
                self.db = self.client[self.config.MONGODB_DATABASE]

                # Set up collection with schema validation
                if "radiologues" not in self.db.list_collection_names():
                    self.db.create_collection("radiologues")
                    self.db.command(
                        {
                            "collMod": "radiologues",
                            "validator": self.config.get_mongodb_validation_schema(),
                        }
                    )

                self.radiologues_collection = self.db["radiologues"]
                logger_service.info("Connected to MongoDB successfully")
                break
            except Exception as e:
                logger_service.error(
                    f"MongoDB connection attempt {attempt+1} failed: {str(e)}"
                )
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger_service.error(
                        "Failed to connect to MongoDB after multiple attempts"
                    )

    def find_radiologues(self, query=None):
        """Find radiologues by query"""
        try:
            query = query or {}
            radiologues = list(self.radiologues_collection.find(query))
            # Convert ObjectId to string
            for radiologue in radiologues:
                radiologue["_id"] = str(radiologue["_id"])
            return radiologues
        except Exception as e:
            logger_service.error(f"MongoDB find_radiologues error: {str(e)}")
            raise

    def find_radiologue_by_id(self, radiologue_id):
        """Find a radiologue by ID"""
        try:
            radiologue = self.radiologues_collection.find_one(
                {"_id": ObjectId(radiologue_id)}
            )
            if radiologue:
                radiologue["_id"] = str(radiologue["_id"])
            return radiologue
        except Exception as e:
            logger_service.error(f"MongoDB find_radiologue_by_id error: {str(e)}")
            return None

    def insert_radiologue(self, radiologue_data):
        """Insert a new radiologue"""
        try:
            radiologue_data["created_at"] = datetime.utcnow()
            radiologue_data["updated_at"] = datetime.utcnow()

            result = self.radiologues_collection.insert_one(radiologue_data)
            radiologue_data["_id"] = str(result.inserted_id)
            return radiologue_data
        except Exception as e:
            logger_service.error(f"MongoDB insert_radiologue error: {str(e)}")
            raise

    def update_radiologue(self, radiologue_id, radiologue_data):
        """Update an existing radiologue"""
        try:
            radiologue_data["updated_at"] = datetime.utcnow()

            result = self.radiologues_collection.update_one(
                {"_id": ObjectId(radiologue_id)}, {"$set": radiologue_data}
            )

            if result.matched_count == 0:
                return None

            radiologue_data["_id"] = radiologue_id
            return radiologue_data
        except Exception as e:
            logger_service.error(f"MongoDB update_radiologue error: {str(e)}")
            raise

    def delete_radiologue(self, radiologue_id):
        """Delete a radiologue"""
        try:
            result = self.radiologues_collection.delete_one(
                {"_id": ObjectId(radiologue_id)}
            )
            return result.deleted_count > 0
        except Exception as e:
            logger_service.error(f"MongoDB delete_radiologue error: {str(e)}")
            raise

    def close(self):
        """Close MongoDB connection"""
        try:
            if self.client:
                self.client.close()
                logger_service.info("Closed MongoDB connection")
        except Exception as e:
            logger_service.error(f"Error closing MongoDB connection: {str(e)}")

    def check_health(self):
        """Check MongoDB health"""
        try:
            self.db.command("ping")
            return "UP"
        except Exception as e:
            return f"DOWN: {str(e)}"
