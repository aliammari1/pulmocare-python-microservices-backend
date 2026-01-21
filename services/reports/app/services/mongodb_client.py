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
        self.reports_collection = None
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
                if "reports" not in self.db.list_collection_names():
                    self.db.create_collection("reports")
                    # self.db.command(
                    #     {
                    #         "collMod": "reports",
                    #         "validator": self.config.get_mongodb_validation_schema(),
                    #     }
                    # )

                self.reports_collection = self.db["reports"]
                logger_service.info("Connected to MongoDB successfully")
                break
            except Exception as e:
                logger_service.error(f"MongoDB connection attempt {attempt + 1} failed: {e!s}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger_service.error("Failed to connect to MongoDB after multiple attempts")

    def find_reports(self, query=None):
        """Find reports by query"""
        try:
            query = query or {}
            reports = list(self.reports_collection.find(query))
            # Convert ObjectId to string
            for report in reports:
                report["_id"] = str(report["_id"])
            return reports
        except Exception as e:
            logger_service.error(f"MongoDB find_reports error: {e!s}")
            raise

    def find_report_by_id(self, report_id):
        """Find a report by ID"""
        try:
            report = self.reports_collection.find_one({"_id": ObjectId(report_id)})
            if report:
                report["_id"] = str(report["_id"])
            return report
        except Exception as e:
            logger_service.error(f"MongoDB find_report_by_id error: {e!s}")
            return None

    def insert_report(self, report_data):
        """Insert a new report"""
        try:
            report_data["created_at"] = datetime.utcnow()
            report_data["updated_at"] = datetime.utcnow()

            result = self.reports_collection.insert_one(report_data)
            report_data["_id"] = str(result.inserted_id)
            return report_data
        except Exception as e:
            logger_service.error(f"MongoDB insert_report error: {e!s}")
            raise

    def update_report(self, report_id, report_data):
        """Update an existing report"""
        try:
            report_data["updated_at"] = datetime.utcnow()

            result = self.reports_collection.update_one({"_id": ObjectId(report_id)}, {"$set": report_data})

            if result.matched_count == 0:
                return None

            report_data["_id"] = report_id
            return report_data
        except Exception as e:
            logger_service.error(f"MongoDB update_report error: {e!s}")
            raise

    def delete_report(self, report_id):
        """Delete a report"""
        try:
            result = self.reports_collection.delete_one({"_id": ObjectId(report_id)})
            return result.deleted_count > 0
        except Exception as e:
            logger_service.error(f"MongoDB delete_report error: {e!s}")
            raise

    def close(self):
        """Close MongoDB connection"""
        try:
            if self.client:
                self.client.close()
                logger_service.info("Closed MongoDB connection")
        except Exception as e:
            logger_service.error(f"Error closing MongoDB connection: {e!s}")

    def check_health(self):
        """Check MongoDB health"""
        try:
            self.db.command("ping")
            return "UP"
        except Exception as e:
            return f"DOWN: {e!s}"
