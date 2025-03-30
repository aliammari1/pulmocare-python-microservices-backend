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
        self.ordonnances_collection = None
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
                if "ordonnances" not in self.db.list_collection_names():
                    self.db.create_collection("ordonnances")
                    self.db.command(
                        {
                            "collMod": "ordonnances",
                            "validator": self.config.get_mongodb_validation_schema(),
                        }
                    )

                self.ordonnances_collection = self.db["ordonnances"]
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

    def find_ordonnances(self, query=None):
        """Find ordonnances by query"""
        try:
            query = query or {}
            ordonnances = list(self.ordonnances_collection.find(query))
            # Convert ObjectId to string
            for ordonnance in ordonnances:
                ordonnance["_id"] = str(ordonnance["_id"])
            return ordonnances
        except Exception as e:
            logger_service.error(f"MongoDB find_ordonnances error: {str(e)}")
            raise

    def find_ordonnance_by_id(self, ordonnance_id):
        """Find a ordonnance by ID"""
        try:
            ordonnance = self.ordonnances_collection.find_one({"_id": ObjectId(ordonnance_id)})
            if ordonnance:
                ordonnance["_id"] = str(ordonnance["_id"])
            return ordonnance
        except Exception as e:
            logger_service.error(f"MongoDB find_ordonnance_by_id error: {str(e)}")
            return None

    def insert_ordonnance(self, ordonnance_data):
        """Insert a new ordonnance"""
        try:
            ordonnance_data["created_at"] = datetime.utcnow()
            ordonnance_data["updated_at"] = datetime.utcnow()

            result = self.ordonnances_collection.insert_one(ordonnance_data)
            ordonnance_data["_id"] = str(result.inserted_id)
            return ordonnance_data
        except Exception as e:
            logger_service.error(f"MongoDB insert_ordonnance error: {str(e)}")
            raise

    def update_ordonnance(self, ordonnance_id, ordonnance_data):
        """Update an existing ordonnance"""
        try:
            ordonnance_data["updated_at"] = datetime.utcnow()

            result = self.ordonnances_collection.update_one(
                {"_id": ObjectId(ordonnance_id)}, {"$set": ordonnance_data}
            )

            if result.matched_count == 0:
                return None

            ordonnance_data["_id"] = ordonnance_id
            return ordonnance_data
        except Exception as e:
            logger_service.error(f"MongoDB update_ordonnance error: {str(e)}")
            raise

    def delete_ordonnance(self, ordonnance_id):
        """Delete a ordonnance"""
        try:
            result = self.ordonnances_collection.delete_one({"_id": ObjectId(ordonnance_id)})
            return result.deleted_count > 0
        except Exception as e:
            logger_service.error(f"MongoDB delete_ordonnance error: {str(e)}")
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
