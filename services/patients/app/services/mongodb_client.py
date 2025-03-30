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
        self.patients_collection = None
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
                if "patients" not in self.db.list_collection_names():
                    self.db.create_collection("patients")
                    self.db.command(
                        {
                            "collMod": "patients",
                            "validator": self.config.get_mongodb_validation_schema(),
                        }
                    )

                self.patients_collection = self.db["patients"]
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

    def find_patients(self, query=None):
        """Find patients by query"""
        try:
            query = query or {}
            patients = list(self.patients_collection.find(query))
            # Convert ObjectId to string
            for patient in patients:
                patient["_id"] = str(patient["_id"])
            return patients
        except Exception as e:
            logger_service.error(f"MongoDB find_patients error: {str(e)}")
            raise

    def find_patient_by_id(self, patient_id):
        """Find a patient by ID"""
        try:
            patient = self.patients_collection.find_one({"_id": ObjectId(patient_id)})
            if patient:
                patient["_id"] = str(patient["_id"])
            return patient
        except Exception as e:
            logger_service.error(f"MongoDB find_patient_by_id error: {str(e)}")
            return None

    def insert_patient(self, patient_data):
        """Insert a new patient"""
        try:
            patient_data["created_at"] = datetime.utcnow()
            patient_data["updated_at"] = datetime.utcnow()

            result = self.patients_collection.insert_one(patient_data)
            patient_data["_id"] = str(result.inserted_id)
            return patient_data
        except Exception as e:
            logger_service.error(f"MongoDB insert_patient error: {str(e)}")
            raise

    def update_patient(self, patient_id, patient_data):
        """Update an existing patient"""
        try:
            patient_data["updated_at"] = datetime.utcnow()

            result = self.patients_collection.update_one(
                {"_id": ObjectId(patient_id)}, {"$set": patient_data}
            )

            if result.matched_count == 0:
                return None

            patient_data["_id"] = patient_id
            return patient_data
        except Exception as e:
            logger_service.error(f"MongoDB update_patient error: {str(e)}")
            raise

    def delete_patient(self, patient_id):
        """Delete a patient"""
        try:
            result = self.patients_collection.delete_one({"_id": ObjectId(patient_id)})
            return result.deleted_count > 0
        except Exception as e:
            logger_service.error(f"MongoDB delete_patient error: {str(e)}")
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
