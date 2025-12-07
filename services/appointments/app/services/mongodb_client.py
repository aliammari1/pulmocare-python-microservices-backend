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
        self.appointments_collection = None
        self.init_connection()

    def init_connection(self):
        """Initialize MongoDB connection with schema validation"""
        max_retries = 5
        retry_delay = 1

        for attempt in range(max_retries):
            try:
                # Use mongodb as the hostname - this is the service name in Docker network
                mongodb_host = self.config.MONGODB_HOST or "mongodb"
                mongodb_port = self.config.MONGODB_PORT or 27017

                # Create the connection string
                connection_string = f"mongodb://{self.config.MONGODB_USERNAME}:{self.config.MONGODB_PASSWORD}@{mongodb_host}:{mongodb_port}/"

                logger_service.info(
                    f"Connecting to MongoDB at {mongodb_host}:{mongodb_port}"
                )
                self.client = MongoClient(
                    connection_string,
                    serverSelectionTimeoutMS=self.config.MONGODB_SERVER_SELECTION_TIMEOUT_MS,
                    connectTimeoutMS=self.config.MONGODB_CONNECT_TIMEOUT_MS,
                    maxPoolSize=self.config.MONGODB_POOL_SIZE,
                    minPoolSize=self.config.MONGODB_MIN_POOL_SIZE,
                )

                # Test the connection
                self.client.admin.command("ping")

                self.db = self.client[self.config.MONGODB_DATABASE]

                # Set up collection with schema validation
                if "appointments" not in self.db.list_collection_names():
                    self.db.create_collection("appointments")
                    # Uncomment to add schema validation
                    # self.db.command(
                    #     {
                    #         "collMod": "appointments",
                    #         "validator": self.config.get_mongodb_validation_schema(),
                    #     }
                    # )

                self.appointments_collection = self.db["appointments"]
                logger_service.info("Connected to MongoDB successfully")
                break
            except Exception as e:
                logger_service.error(
                    f"MongoDB connection attempt {attempt + 1} failed: {str(e)}"
                )
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger_service.error(
                        "Failed to connect to MongoDB after multiple attempts"
                    )

    def find_appointments(self, query=None):
        """Find appointments by query"""
        try:
            query = query or {}
            appointments = list(self.appointments_collection.find(query))
            # Convert ObjectId to string
            for appointment in appointments:
                appointment["_id"] = str(appointment["_id"])
            return appointments
        except Exception as e:
            logger_service.error(f"MongoDB find_appointments error: {str(e)}")
            raise

    def find_appointment_by_id(self, appointment_id):
        """Find an appointment by ID"""
        try:
            appointment = self.appointments_collection.find_one(
                {"_id": ObjectId(appointment_id)}
            )
            if appointment:
                appointment["_id"] = str(appointment["_id"])
            return appointment
        except Exception as e:
            logger_service.error(f"MongoDB find_appointment_by_id error: {str(e)}")
            return None

    def find_appointments_by_patient(self, patient_id):
        """Find appointments for a specific patient"""
        try:
            appointments = list(
                self.appointments_collection.find({"patient_id": patient_id})
            )
            for appointment in appointments:
                appointment["_id"] = str(appointment["_id"])
            return appointments
        except Exception as e:
            logger_service.error(
                f"MongoDB find_appointments_by_patient error: {str(e)}"
            )
            raise

    def find_appointments_by_provider(self, provider_id):
        """Find appointments for a specific provider (doctor/radiologist)"""
        try:
            appointments = list(
                self.appointments_collection.find({"provider_id": provider_id})
            )
            for appointment in appointments:
                appointment["_id"] = str(appointment["_id"])
            return appointments
        except Exception as e:
            logger_service.error(
                f"MongoDB find_appointments_by_provider error: {str(e)}"
            )
            raise

    def insert_appointment(self, appointment_data):
        """Insert a new appointment"""
        try:
            appointment_data["created_at"] = datetime.utcnow()
            appointment_data["updated_at"] = datetime.utcnow()

            result = self.appointments_collection.insert_one(appointment_data)
            appointment_data["_id"] = str(result.inserted_id)
            return appointment_data
        except Exception as e:
            logger_service.error(f"MongoDB insert_appointment error: {str(e)}")
            raise

    def update_appointment(self, appointment_id, appointment_data):
        """Update an existing appointment"""
        try:
            appointment_data["updated_at"] = datetime.utcnow()

            result = self.appointments_collection.update_one(
                {"_id": ObjectId(appointment_id)}, {"$set": appointment_data}
            )

            if result.matched_count == 0:
                return None

            appointment_data["_id"] = appointment_id
            return appointment_data
        except Exception as e:
            logger_service.error(f"MongoDB update_appointment error: {str(e)}")
            raise

    def delete_appointment(self, appointment_id):
        """Delete an appointment"""
        try:
            result = self.appointments_collection.delete_one(
                {"_id": ObjectId(appointment_id)}
            )
            return result.deleted_count > 0
        except Exception as e:
            logger_service.error(f"MongoDB delete_appointment error: {str(e)}")
            raise

    def close(self):
        """Close MongoDB connection"""
        try:
            if self.client:
                self.client.close()
                logger_service.info("Closed MongoDB connection")
        except Exception as e:
            logger_service.error(f"Error closing MongoDB connection: {str(e)}")

    async def close_async(self):
        """Asynchronously close MongoDB connection"""
        # MongoDB driver doesn't have an async close method, but we use this
        # to be consistent with async/await pattern in the application
        self.close()
        return True

    def check_health(self):
        """Check MongoDB health"""
        try:
            self.db.command("ping")
            return "UP"
        except Exception as e:
            return f"DOWN: {str(e)}"
