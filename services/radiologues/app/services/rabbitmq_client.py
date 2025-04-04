import json
import socket
import time
from datetime import datetime
from typing import Any, Callable, Dict

import pika
import pika.exceptions
from services.logger_service import logger_service
from services.metrics import (RABBITMQ_MESSAGES_PUBLISHED,
                              RABBITMQ_PUBLISH_LATENCY)

from config import Config


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
            logger_service.error(f"RabbitMQ error: {str(e)}")
            return False

    return wrapper


class RabbitMQClient:
    """Client for RabbitMQ messaging"""

    def __init__(self, config: Config):
        """Initialize RabbitMQ client"""
        self.config = config
        self.connection = None
        self.channel = None

        # Set up connection to RabbitMQ
        self._setup_connection()

    def _setup_connection(self):
        """Set up connection to RabbitMQ"""
        try:
            # Create credentials and connection parameters
            credentials = pika.PlainCredentials(
                self.config.RABBITMQ_USER, self.config.RABBITMQ_PASS
            )
            parameters = pika.ConnectionParameters(
                host=self.config.RABBITMQ_HOST,
                port=self.config.RABBITMQ_PORT,
                virtual_host=self.config.RABBITMQ_VHOST,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300,
            )

            # Create connection and channel
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()

            # Declare exchanges for different message types
            self.channel.exchange_declare(
                exchange="medical.events", exchange_type="topic", durable=True
            )
            self.channel.exchange_declare(
                exchange="medical.commands", exchange_type="direct", durable=True
            )
            self.channel.exchange_declare(
                exchange="medical.reports", exchange_type="topic", durable=True
            )

            # Declare queues for radiologues service
            self.channel.queue_declare(queue="radiologues.reports", durable=True)
            self.channel.queue_declare(queue="radiologues.analysis", durable=True)
            self.channel.queue_declare(queue="radiologues.notifications", durable=True)
            self.channel.queue_declare(queue="radiologues.examinations", durable=True)

            # Bind queues to exchanges with appropriate routing keys
            self.channel.queue_bind(
                exchange="medical.reports",
                queue="radiologues.reports",
                routing_key="report.created",
            )

            self.channel.queue_bind(
                exchange="medical.reports",
                queue="radiologues.analysis",
                routing_key="report.analysis.requested",
            )

            self.channel.queue_bind(
                exchange="medical.events",
                queue="radiologues.notifications",
                routing_key="radiologue.#",
            )

            # New binding for radiology examination requests from doctors
            self.channel.queue_bind(
                exchange="medical.reports",
                queue="radiologues.examinations",
                routing_key="report.examination.requested",
            )

            logger_service.info("Successfully connected to RabbitMQ")

        except Exception as e:
            logger_service.error(f"Failed to connect to RabbitMQ: {str(e)}")

    @track_rabbitmq_metrics
    def publish_message(self, exchange: str, routing_key: str, message: Dict[str, Any]):
        """Publish a message to RabbitMQ"""
        try:
            if not self.connection or self.connection.is_closed:
                self._setup_connection()

            # Convert message to JSON and publish
            message_body = json.dumps(message)
            self.channel.basic_publish(
                exchange=exchange,
                routing_key=routing_key,
                body=message_body,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # persistent
                    content_type="application/json",
                    timestamp=int(time.time()),
                    message_id=f"{socket.gethostname()}-{time.time()}",
                    headers={"service": "radiologues-service"},
                ),
            )

            logger_service.info(f"Published message to {exchange}:{routing_key}")
            return True

        except Exception as e:
            logger_service.error(f"Failed to publish message: {str(e)}")
            return False

    def consume_messages(self, queue_name: str, callback: Callable):
        """Set up a consumer for the specified queue"""
        if not self.connection or self.connection.is_closed:
            self._setup_connection()

        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(queue=queue_name, on_message_callback=callback)
        logger_service.info(f"Started consuming messages from {queue_name}")

    def publish_radiology_report(self, report_id: str, report_data: Dict[str, Any]):
        """Publish a radiology report to the analysis service"""
        message = {
            "report_id": report_id,
            "report_data": report_data,
            "timestamp": datetime.utcnow().isoformat(),
        }

        return self.publish_message(
            exchange="medical.reports",
            routing_key="report.analysis.requested",
            message=message,
        )

    def publish_examination_result(
        self,
        request_id: str,
        doctor_id: str,
        patient_id: str,
        exam_type: str,
        report_id: str,
    ):
        """Notify about a completed radiology examination"""
        message = {
            "request_id": request_id,
            "doctor_id": doctor_id,
            "patient_id": patient_id,
            "exam_type": exam_type,
            "report_id": report_id,
            "status": "completed",
            "timestamp": datetime.utcnow().isoformat(),
        }

        return self.publish_message(
            exchange="medical.reports",
            routing_key="report.examination.completed",
            message=message,
        )

    def notify_doctor_report_ready(
        self, report_id: str, doctor_id: str, patient_id: str, exam_type: str
    ):
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
            routing_key=f"doctor.report.ready",
            message=message,
        )

    def close(self):
        """Close the RabbitMQ connection"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
            logger_service.info("RabbitMQ connection closed")
