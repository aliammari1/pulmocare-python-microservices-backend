from services.logger_service import logger_service


class ReportService:
    """Service for report business logic"""

    def __init__(self, mongodb_client, redis_client, rabbitmq_client):
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client
        self.rabbitmq_client = rabbitmq_client

    def get_all_reports(self, search=None):
        """Get all reports with optional filtering"""
        try:
            query = {}
            if search:
                query = {
                    "$or": [
                        {"title": {"$regex": search, "$options": "i"}},
                        {"content": {"$regex": search, "$options": "i"}},
                    ]
                }
            return self.mongodb_client.find_reports(query)
        except Exception as e:
            logger_service.error(f"Error getting reports: {str(e)}")
            raise

    def get_report_by_id(self, report_id):
        """Get a specific report by ID with caching"""
        try:
            # Try cache first
            cached_report = self.redis_client.get_report(report_id)
            if cached_report:
                return cached_report

            # Fetch from database if not in cache
            report = self.mongodb_client.find_report_by_id(report_id)
            if report:
                # Cache for next time
                self.redis_client.cache_report(report_id, report)

            return report
        except Exception as e:
            logger_service.error(f"Error getting report {report_id}: {str(e)}")
            raise

    def get_raw_report(self, report_id):
        """Get raw report data (needed for PDF generation)"""
        try:
            return self.mongodb_client.find_report_by_id(report_id)
        except Exception as e:
            logger_service.error(f"Error getting raw report {report_id}: {str(e)}")
            raise

    def create_report(self, report_data):
        """Create a new report"""
        try:
            # Insert into database
            report = self.mongodb_client.insert_report(report_data)

            # Publish event for analysis
            self.rabbitmq_client.publish_report_created(report["_id"])

            return report
        except Exception as e:
            logger_service.error(f"Error creating report: {str(e)}")
            raise

    def update_report(self, report_id, report_data):
        """Update an existing report"""
        try:
            # Update in database
            updated_report = self.mongodb_client.update_report(report_id, report_data)

            if updated_report:
                # Invalidate cache
                self.redis_client.invalidate_report(report_id)

                # Publish event
                self.rabbitmq_client.publish_report_updated(report_id)

            return updated_report
        except Exception as e:
            logger_service.error(f"Error updating report {report_id}: {str(e)}")
            raise

    def delete_report(self, report_id):
        """Delete a report"""
        try:
            # Delete from database
            success = self.mongodb_client.delete_report(report_id)

            if success:
                # Invalidate cache
                self.redis_client.invalidate_report(report_id)

                # Publish event
                self.rabbitmq_client.publish_report_deleted(report_id)

            return success
        except Exception as e:
            logger_service.error(f"Error deleting report {report_id}: {str(e)}")
            raise
