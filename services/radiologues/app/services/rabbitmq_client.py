import json
import os
import time
from datetime import datetime
from typing import Any

import pika
import pika.exceptions
from pika.adapters.blocking_connection import BlockingChannel
from pika.exchange_type import ExchangeType

from services.logger_service import logger_service
from services.metrics import RABBITMQ_MESSAGES_PUBLISHED, RABBITMQ_PUBLISH_LATENCY


def track_rabbitmq_metrics(func):
    """Decorator to track RabbitMQ metrics"""

    def wrapper(self, *args, **kwargs):
        start_time = time.time()
        try:
            result = func(self, *args, **kwargs)
            latency = time.time() - start_time
            RABBITMQ_PUBLISH_LATENCY.record(latency)
            RABBITMQ_MESSAGES_PUBLISHED.add(1)
            return result
        except Exception as e:
            logger_service.error(f"RabbitMQ error: {e!s}")
            return False

    return wrapper


class RabbitMQClient:
    """
    Client for RabbitMQ messaging between microservices.
    """

    def __init__(self, config):
        """
        Initialize the RabbitMQ client with configuration.
        """
        # Get RabbitMQ connection parameters from environment variables or config
        self.host = os.getenv("RABBITMQ_HOST", config.RABBITMQ_HOST)
        self.port = int(os.getenv("RABBITMQ_PORT", config.RABBITMQ_PORT))
        self.username = os.getenv("RABBITMQ_USER", config.RABBITMQ_USER)
        self.password = os.getenv("RABBITMQ_PASS", config.RABBITMQ_PASS)
        self.virtual_host = os.getenv("RABBITMQ_VHOST", config.RABBITMQ_VHOST)
        self.connection = None
        self.channel = None
        self.service_name = "radiologues"  # Name of this service for routing keys

        # Define exchange names for different domains
        self.exchanges = {
            "medical": "medical.exchange",
            "radiology": "radiology.exchange",
            "reports": "reports.exchange",
            "notifications": "notifications.exchange",
        }

    def connect(self) -> BlockingChannel:
        """
        Create a connection to RabbitMQ and return a channel.
        """
        try:
            # Create connection parameters
            credentials = pika.PlainCredentials(self.username, self.password)
            parameters = pika.ConnectionParameters(
                host=self.host,
                port=self.port,
                virtual_host=self.virtual_host,
                credentials=credentials,
                heartbeat=600,  # 10 minutes heartbeat
                blocked_connection_timeout=300,  # 5 minutes timeout
            )

            # Create a connection
            self.connection = pika.BlockingConnection(parameters)

            # Create a channel
            self.channel = self.connection.channel()

            # Declare exchanges that we'll use
            self._declare_exchanges()

            logger_service.info(f"Connected to RabbitMQ at {self.host}:{self.port}")
            return self.channel

        except Exception as e:
            logger_service.error(f"Failed to connect to RabbitMQ: {e}")
            raise

    def disconnect(self) -> None:
        """
        Close the RabbitMQ connection.
        """
        if self.connection and self.connection.is_open:
            self.connection.close()
            self.connection = None
            self.channel = None
            logger_service.info("Disconnected from RabbitMQ")

    def _declare_exchanges(self) -> None:
        """
        Declare the exchanges we'll use for messaging.
        """
        if not self.channel:
            return

        # Declare exchanges with appropriate types
        for name, exchange in self.exchanges.items():
            self.channel.exchange_declare(
                exchange=exchange,
                exchange_type=ExchangeType.topic,
                durable=True,
                auto_delete=False,
            )

    def _get_channel(self) -> BlockingChannel:
        """
        Get an active channel, creating a connection if needed.
        """
        if not self.channel or not self.connection or self.connection.is_closed:
            return self.connect()
        return self.channel

    @track_rabbitmq_metrics
    def publish_message(self, exchange: str, routing_key: str, message: dict[str, Any]) -> bool:
        """
        Publish a message to RabbitMQ.

        Args:
            exchange: Exchange name to publish to
            routing_key: Routing key for message
            message: Message dictionary to publish

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            channel = self._get_channel()

            # Add timestamp if not present
            if "timestamp" not in message:
                message["timestamp"] = datetime.utcnow().isoformat()

            # Add service identifier
            if "service" not in message:
                message["service"] = self.service_name

            # Convert message to JSON
            message_json = json.dumps(message)

            # Publish the message
            channel.basic_publish(
                exchange=exchange,
                routing_key=routing_key,
                body=message_json,
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,  # make message persistent
                ),
            )

            logger_service.info(f"Published message to exchange={exchange}, routing_key={routing_key}")
            return True

        except Exception as e:
            logger_service.error(f"Failed to publish message: {e}")
            # Try to reconnect and publish again
            try:
                self.connect()
                channel = self._get_channel()
                message_json = json.dumps(message)

                channel.basic_publish(
                    exchange=exchange,
                    routing_key=routing_key,
                    body=message_json,
                    properties=pika.BasicProperties(
                        content_type="application/json",
                        delivery_mode=2,
                    ),
                )

                logger_service.info(f"Successfully republished message after reconnect to {exchange}, routing_key={routing_key}")
                return True
            except Exception as retry_error:
                logger_service.error(f"Failed to republish message after reconnect: {retry_error}")
                return False

    def send_radiology_report(
        self,
        report_id: str,
        doctor_id: str,
        patient_id: str,
        radiologist_id: str,
        exam_type: str,
        findings: str,
        impression: str,
        images_urls: list = None,
    ) -> bool:
        """
        Send a radiology report to the reports exchange.

        Args:
            report_id: Unique ID of the report
            doctor_id: ID of the doctor who requested the examination
            patient_id: ID of the patient
            radiologist_id: ID of the radiologist who created the report
            exam_type: Type of examination (e.g., X-ray, CT scan)
            findings: Findings of the examination
            impression: Impression/conclusion of the examination
            images_urls: Optional list of URLs to examination images

        Returns:
            bool: True if successful, False otherwise
        """
        message = {
            "report_id": report_id,
            "doctor_id": doctor_id,
            "patient_id": patient_id,
            "radiologist_id": radiologist_id,
            "exam_type": exam_type,
            "findings": findings,
            "impression": impression,
            "images_urls": images_urls or [],
            "created_at": datetime.utcnow().isoformat(),
            "event": "radiology_report_created",
            "service": self.service_name,
        }

        # Publish to the reports exchange
        return self.publish_message(
            exchange=self.exchanges["reports"],
            routing_key="report.radiology.created",
            message=message,
        )

    def update_radiology_report_status(
        self,
        report_id: str,
        status: str,
        updated_by: str,
    ) -> bool:
        """
        Update the status of a radiology report.

        Args:
            report_id: Unique ID of the report
            status: New status (e.g., "in_progress", "completed", "cancelled")
            updated_by: ID of the user who updated the status

        Returns:
            bool: True if successful, False otherwise
        """
        message = {
            "report_id": report_id,
            "status": status,
            "updated_by": updated_by,
            "updated_at": datetime.utcnow().isoformat(),
            "event": "radiology_report_status_updated",
            "service": self.service_name,
        }

        # Publish to the reports exchange
        return self.publish_message(
            exchange=self.exchanges["reports"],
            routing_key=f"report.radiology.status.{status}",
            message=message,
        )

    def accept_radiology_examination(
        self,
        request_id: str,
        radiologist_id: str,
        estimated_completion_date: str = None,
    ) -> bool:
        """
        Accept a radiology examination request.

        Args:
            request_id: ID of the radiology examination request
            radiologist_id: ID of the radiologist accepting the request
            estimated_completion_date: Optional estimated completion date

        Returns:
            bool: True if successful, False otherwise
        """
        message = {
            "request_id": request_id,
            "radiologist_id": radiologist_id,
            "status": "accepted",
            "estimated_completion_date": estimated_completion_date,
            "accepted_at": datetime.utcnow().isoformat(),
            "event": "radiology_request_accepted",
            "service": self.service_name,
        }

        # Publish to the radiology exchange
        return self.publish_message(
            exchange=self.exchanges["radiology"],
            routing_key="radiology.request.accepted",
            message=message,
        )

    def reject_radiology_examination(self, request_id: str, radiologist_id: str, reason: str) -> bool:
        """
        Reject a radiology examination request.

        Args:
            request_id: ID of the radiology examination request
            radiologist_id: ID of the radiologist rejecting the request
            reason: Reason for rejection

        Returns:
            bool: True if successful, False otherwise
        """
        message = {
            "request_id": request_id,
            "radiologist_id": radiologist_id,
            "status": "rejected",
            "reason": reason,
            "rejected_at": datetime.utcnow().isoformat(),
            "event": "radiology_request_rejected",
            "service": self.service_name,
        }

        # Publish to the radiology exchange
        return self.publish_message(
            exchange=self.exchanges["radiology"],
            routing_key="radiology.request.rejected",
            message=message,
        )

    def send_notification(
        self,
        recipient_id: str,
        recipient_type: str,
        notification_type: str,
        message: str,
        data: dict = None,
    ) -> bool:
        """
        Send a notification to a user.

        Args:
            recipient_id: ID of the recipient
            recipient_type: Type of recipient (doctor, patient, radiologist)
            notification_type: Type of notification
            message: Notification message
            data: Additional data for the notification

        Returns:
            bool: True if successful, False otherwise
        """
        notification = {
            "recipient_id": recipient_id,
            "recipient_type": recipient_type,
            "notification_type": notification_type,
            "message": message,
            "data": data or {},
            "sent_at": datetime.utcnow().isoformat(),
            "service": self.service_name,
        }

        # Publish to the notifications exchange
        return self.publish_message(
            exchange=self.exchanges["notifications"],
            routing_key=f"notification.{recipient_type}.{notification_type}",
            message=notification,
        )

    def setup_radiology_request_consumer(self, callback) -> None:
        """
        Setup a consumer for radiology examination requests from doctors.

        Args:
            callback: Function to call when a message is received
        """
        channel = self._get_channel()

        # Declare a queue for this service to receive radiology requests
        result = channel.queue_declare(
            queue=f"{self.service_name}.radiology.requests",
            durable=True,
            exclusive=False,
            auto_delete=False,
        )
        queue_name = result.method.queue

        # Bind the queue to relevant routing keys
        channel.queue_bind(
            exchange=self.exchanges["radiology"],
            queue=queue_name,
            routing_key="radiology.request.created",
        )

        # Set QoS to limit messages processed at once
        channel.basic_qos(prefetch_count=1)

        # Set up the consumer
        channel.basic_consume(
            queue=queue_name,
            on_message_callback=callback,
            auto_ack=False,  # We'll acknowledge manually after processing
        )

        logger_service.info(f"Set up consumer for queue {queue_name}")

        # Start consuming (this will block until channel.stop_consuming() is called)
        try:
            logger_service.info("Starting to consume messages...")
            channel.start_consuming()
        except KeyboardInterrupt:
            channel.stop_consuming()
            logger_service.info("Consumer stopped")
        except Exception as e:
            logger_service.error(f"Consumer error: {e}")
            channel.stop_consuming()

    def acknowledge_message(self, delivery_tag: int) -> None:
        """
        Acknowledge a message.

        Args:
            delivery_tag: Delivery tag of the message to acknowledge
        """
        if self.channel and self.channel.is_open:
            self.channel.basic_ack(delivery_tag=delivery_tag)
            logger_service.debug(f"Acknowledged message with tag {delivery_tag}")

    def reject_message(self, delivery_tag: int, requeue: bool = False) -> None:
        """
        Reject a message.

        Args:
            delivery_tag: Delivery tag of the message to reject
            requeue: Whether to requeue the message
        """
        if self.channel and self.channel.is_open:
            self.channel.basic_reject(delivery_tag=delivery_tag, requeue=requeue)
            logger_service.debug(f"Rejected message with tag {delivery_tag}, requeue={requeue}")

    def notify_doctor_report_ready(self, report_id: str, doctor_id: str, patient_id: str, exam_type: str):
        """Notify a doctor that a requested report is ready"""
        message = {
            "report_id": report_id,
            "doctor_id": doctor_id,
            "patient_id": patient_id,
            "exam_type": exam_type,
            "event": "report_ready",
            "timestamp": datetime.utcnow().isoformat(),
        }

        return self.publish_message(
            exchange="medical.events",
            routing_key="doctor.report.ready",
            message=message,
        )

    def close(self):
        """Close the RabbitMQ connection"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
            logger_service.info("RabbitMQ connection closed")
