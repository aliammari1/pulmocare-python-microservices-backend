import json
import threading
from datetime import datetime
from typing import Any, Dict

from services.logger_service import logger_service
from services.message_broker import MessageBroker
from services.mongodb_client import MongoDBClient
from services.redis_client import RedisClient

from config import Config


class MessageConsumer:
    """Consumer for processing messages from RabbitMQ queues"""

    def __init__(
        self, config: Config, mongodb_client: MongoDBClient, redis_client: RedisClient
    ):
        """Initialize the message consumer with dependencies"""
        self.config = config
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client
        self.message_broker = MessageBroker(config)
        self.consumers = []

    def start_consumers(self):
        """Start consumers for all relevant queues"""
        self._start_consumer("reports.processing", self._handle_report_processing)
        self._start_consumer("reports.analysis", self._handle_report_analysis)
        self._start_consumer("reports.notifications", self._handle_report_notification)

    def _start_consumer(self, queue_name: str, callback):
        """Start a consumer for a specific queue in a separate thread"""
        consumer_thread = threading.Thread(
            target=self._consume, args=(queue_name, callback), daemon=True
        )
        self.consumers.append(consumer_thread)
        consumer_thread.start()
        logger_service.info(f"Started consumer for {queue_name}")

    def _consume(self, queue_name: str, callback):
        """Consume messages from the specified queue"""
        try:
            # Create a separate message broker connection for each consumer
            broker = MessageBroker(self.config)
            broker.consume_messages(queue_name, callback)
        except Exception as e:
            logger_service.error(f"Error in consumer for {queue_name}: {str(e)}")

    def _handle_report_processing(self, channel, method, properties, body):
        """Handle report processing messages"""
        try:
            message = json.loads(body)
            report_id = message.get("report_id")

            logger_service.info(f"Processing report: {report_id}")

            # Acknowledge message immediately to prevent redelivery
            channel.basic_ack(delivery_tag=method.delivery_tag)

            # Perform report processing tasks
            self._process_report(report_id, message)
        except Exception as e:
            logger_service.error(f"Error processing report: {str(e)}")
            # Acknowledge the message even on error to prevent redelivery loops
            channel.basic_ack(delivery_tag=method.delivery_tag)

    def _handle_report_analysis(self, channel, method, properties, body):
        """Handle report analysis request messages"""
        try:
            message = json.loads(body)
            report_id = message.get("report_id")

            logger_service.info(f"Analyzing report: {report_id}")

            # Acknowledge message immediately
            channel.basic_ack(delivery_tag=method.delivery_tag)

            # Perform report analysis tasks
            self._analyze_report(report_id, message)
        except Exception as e:
            logger_service.error(f"Error analyzing report: {str(e)}")
            channel.basic_ack(delivery_tag=method.delivery_tag)

    def _handle_report_notification(self, channel, method, properties, body):
        """Handle report notification messages"""
        try:
            message = json.loads(body)
            report_id = message.get("report_id")
            event = message.get("event")

            logger_service.info(
                f"Received notification for report {report_id}: {event}"
            )

            # Acknowledge message immediately
            channel.basic_ack(delivery_tag=method.delivery_tag)

            # Process the notification
            self._process_notification(report_id, event, message)
        except Exception as e:
            logger_service.error(f"Error processing notification: {str(e)}")
            channel.basic_ack(delivery_tag=method.delivery_tag)

    def _process_report(self, report_id: str, message: Dict[str, Any]):
        """Process a report based on the message"""
        try:
            # Get the report from MongoDB
            report = self.mongodb_client.db.reports.find_one({"_id": report_id})

            if not report:
                logger_service.warning(f"Report {report_id} not found")
                return

            # Update report status to processing
            self.mongodb_client.db.reports.update_one(
                {"_id": report_id},
                {
                    "$set": {
                        "status": "processing",
                        "processing_started_at": datetime.utcnow(),
                    }
                },
            )

            # Notify about processing start
            self.message_broker.publish_message(
                exchange="medical.reports",
                routing_key="report.processing.started",
                message={
                    "report_id": report_id,
                    "event": "processing_started",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

            # Simulate processing delay (would be actual processing in production)
            # In a real implementation, this would be a more complex workflow

            # Update report status to processed
            self.mongodb_client.db.reports.update_one(
                {"_id": report_id},
                {
                    "$set": {
                        "status": "processed",
                        "processing_completed_at": datetime.utcnow(),
                    }
                },
            )

            # Notify about processing completion
            self.message_broker.publish_message(
                exchange="medical.reports",
                routing_key="report.processing.completed",
                message={
                    "report_id": report_id,
                    "event": "processing_completed",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

            logger_service.info(f"Successfully processed report {report_id}")

        except Exception as e:
            logger_service.error(f"Error in _process_report: {str(e)}")

            # Update report with error status
            self.mongodb_client.db.reports.update_one(
                {"_id": report_id},
                {
                    "$set": {
                        "status": "error",
                        "error": str(e),
                        "error_timestamp": datetime.utcnow(),
                    }
                },
            )

            # Notify about processing error
            self.message_broker.publish_message(
                exchange="medical.reports",
                routing_key="report.processing.error",
                message={
                    "report_id": report_id,
                    "error": str(e),
                    "event": "processing_error",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

    def _analyze_report(self, report_id: str, message: Dict[str, Any]):
        """Analyze a report"""
        try:
            # Get the report from MongoDB
            report = self.mongodb_client.db.reports.find_one({"_id": report_id})

            if not report:
                logger_service.warning(f"Report {report_id} not found for analysis")
                return

            # Update report status to analyzing
            self.mongodb_client.db.reports.update_one(
                {"_id": report_id},
                {
                    "$set": {
                        "analysis_status": "analyzing",
                        "analysis_started_at": datetime.utcnow(),
                    }
                },
            )

            # Notify about analysis start
            self.message_broker.publish_message(
                exchange="medical.reports",
                routing_key="report.analysis.started",
                message={
                    "report_id": report_id,
                    "event": "analysis_started",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

            # Simulated analysis (in a real implementation, this would be more complex)
            # E.g., call to an AI service, image analysis, etc.
            analysis_results = {
                "findings": [],
                "technical_details": {
                    "quality_metrics": {"image_quality": 0.92, "confidence": 0.89}
                },
                "analyzed_at": datetime.utcnow().isoformat(),
            }

            # Update report with analysis results
            self.mongodb_client.db.reports.update_one(
                {"_id": report_id},
                {
                    "$set": {
                        "analysis": analysis_results,
                        "analysis_status": "completed",
                        "analysis_completed_at": datetime.utcnow(),
                    }
                },
            )

            # Notify about analysis completion
            self.message_broker.publish_message(
                exchange="medical.reports",
                routing_key="report.analysis.completed",
                message={
                    "report_id": report_id,
                    "analysis": analysis_results,
                    "event": "analysis_completed",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

            logger_service.info(f"Successfully analyzed report {report_id}")

        except Exception as e:
            logger_service.error(f"Error in _analyze_report: {str(e)}")

            # Update report with error status
            self.mongodb_client.db.reports.update_one(
                {"_id": report_id},
                {
                    "$set": {
                        "analysis_status": "error",
                        "analysis_error": str(e),
                        "analysis_error_timestamp": datetime.utcnow(),
                    }
                },
            )

            # Notify about analysis error
            self.message_broker.publish_message(
                exchange="medical.reports",
                routing_key="report.analysis.error",
                message={
                    "report_id": report_id,
                    "error": str(e),
                    "event": "analysis_error",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

    def _process_notification(
        self, report_id: str, event: str, message: Dict[str, Any]
    ):
        """Process a report notification"""
        try:
            # Handle different notification types
            if event == "report_viewed":
                # Track viewing stats
                self.mongodb_client.db.report_stats.update_one(
                    {"report_id": report_id},
                    {
                        "$inc": {"view_count": 1},
                        "$push": {
                            "views": {
                                "timestamp": datetime.utcnow(),
                                "user_id": message.get("user_id"),
                            }
                        },
                    },
                    upsert=True,
                )

            elif event == "report_shared":
                # Track sharing stats
                self.mongodb_client.db.report_stats.update_one(
                    {"report_id": report_id},
                    {
                        "$inc": {"share_count": 1},
                        "$push": {
                            "shares": {
                                "timestamp": datetime.utcnow(),
                                "shared_by": message.get("user_id"),
                                "shared_with": message.get("shared_with"),
                            }
                        },
                    },
                    upsert=True,
                )

            # Store notification in database for audit/history
            self.mongodb_client.db.report_notifications.insert_one(
                {
                    "report_id": report_id,
                    "event": event,
                    "message": message,
                    "processed_at": datetime.utcnow(),
                }
            )

            logger_service.info(
                f"Processed notification for report {report_id}: {event}"
            )

        except Exception as e:
            logger_service.error(f"Error processing notification: {str(e)}")

    def stop(self):
        """Stop all consumers"""
        if self.message_broker:
            self.message_broker.close()
            logger_service.info("Message broker connection closed")
