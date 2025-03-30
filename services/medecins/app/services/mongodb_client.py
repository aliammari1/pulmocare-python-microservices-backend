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
        self.doctors_collection = None
        self.init_connection()

    def init_connection(self):
        """Initialize MongoDB connection with schema validation"""
        max_retries = 5
        retry_delay = 1

        for attempt in range(max_retries):
            try:
                self.client = MongoClient(f"mongodb://admin:admin@{self.config.MONGODB_HOST}:27017/")
                self.db = self.client[self.config.MONGODB_DATABASE]

                # Set up collection with schema validation
                if "doctors" not in self.db.list_collection_names():
                    self.db.create_collection("doctors")
                    self.db.command(
                        {
                            "collMod": "doctors",
                            "validator": self.config.get_mongodb_validation_schema(),
                        }
                    )

                self.doctors_collection = self.db["doctors"]
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

    def find_doctors(self, query=None):
        """Find doctors by query"""
        try:
            query = query or {}
            doctors = list(self.doctors_collection.find(query))
            # Convert ObjectId to string
            for doctor in doctors:
                doctor["_id"] = str(doctor["_id"])
            return doctors
        except Exception as e:
            logger_service.error(f"MongoDB find_doctors error: {str(e)}")
            raise

    def find_doctor_by_id(self, doctor_id):
        """Find a doctor by ID"""
        try:
            doctor = self.doctors_collection.find_one({"_id": ObjectId(doctor_id)})
            if doctor:
                doctor["_id"] = str(doctor["_id"])
            return doctor
        except Exception as e:
            logger_service.error(f"MongoDB find_doctor_by_id error: {str(e)}")
            return None

    def insert_doctor(self, doctor_data):
        """Insert a new doctor"""
        try:
            doctor_data["created_at"] = datetime.utcnow()
            doctor_data["updated_at"] = datetime.utcnow()

            result = self.doctors_collection.insert_one(doctor_data)
            doctor_data["_id"] = str(result.inserted_id)
            return doctor_data
        except Exception as e:
            logger_service.error(f"MongoDB insert_doctor error: {str(e)}")
            raise

    def update_doctor(self, doctor_id, doctor_data):
        """Update an existing doctor"""
        try:
            doctor_data["updated_at"] = datetime.utcnow()

            result = self.doctors_collection.update_one(
                {"_id": ObjectId(doctor_id)}, {"$set": doctor_data}
            )

            if result.matched_count == 0:
                return None

            doctor_data["_id"] = doctor_id
            return doctor_data
        except Exception as e:
            logger_service.error(f"MongoDB update_doctor error: {str(e)}")
            raise

    def delete_doctor(self, doctor_id):
        """Delete a doctor"""
        try:
            result = self.doctors_collection.delete_one({"_id": ObjectId(doctor_id)})
            return result.deleted_count > 0
        except Exception as e:
            logger_service.error(f"MongoDB delete_doctor error: {str(e)}")
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
