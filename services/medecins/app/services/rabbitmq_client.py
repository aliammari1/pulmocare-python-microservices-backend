import functools
import json
import socket
import time
from typing import Any, Callable, Dict, Optional

import pika
from services.logger_service import logger_service
from services.metrics import (RABBITMQ_MESSAGES_PUBLISHED,
                              RABBITMQ_PUBLISH_LATENCY,
                              track_circuit_breaker_failure,
                              track_dependency_status)

from config import Config


def track_rabbitmq_metrics(func):
    """Decorator to track RabbitMQ metrics"""

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        start_time = time.time()
        result = func(self, *args, **kwargs)
        RABBITMQ_PUBLISH_LATENCY.record(time.time() - start_time)
        RABBITMQ_MESSAGES_PUBLISHED.add(1)
        return result

    return wrapper


class RabbitMQClient:
    """Client for RabbitMQ messaging"""

    def __init__(self, config: Config):
        """Initialize RabbitMQ client"""
        self.config = config
        self.connection = None
        self.channel = None
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
                exchange="medical.appointments", exchange_type="topic", durable=True
            )
            self.channel.exchange_declare(
                exchange="medical.prescriptions", exchange_type="topic", durable=True
            )
            self.channel.exchange_declare(
                exchange="medical.reports", exchange_type="topic", durable=True
            )

            # Declare queues for medecins service
            self.channel.queue_declare(queue="appointment.requests", durable=True)
            self.channel.queue_declare(queue="doctor.notifications", durable=True)
            self.channel.queue_declare(queue="prescription.events", durable=True)
            self.channel.queue_declare(queue="patient.events", durable=True)
            # New queue for radiology reports
            self.channel.queue_declare(queue="doctor.radiology.reports", durable=True)

            # Bind queues to exchanges with appropriate routing keys
            self.channel.queue_bind(
                exchange="medical.appointments",
                queue="appointment.requests",
                routing_key="appointment.created",
            )

            self.channel.queue_bind(
                exchange="medical.events",
                queue="doctor.notifications",
                routing_key="doctor.#",
            )

            self.channel.queue_bind(
                exchange="medical.events",
                queue="doctor.notifications",
                routing_key="report.completed",
            )

            self.channel.queue_bind(
                exchange="medical.prescriptions",
                queue="prescription.events",
                routing_key="prescription.#",
            )

            self.channel.queue_bind(
                exchange="medical.events",
                queue="patient.events",
                routing_key="patient.#",
            )

            # New bindings for radiology reports
            self.channel.queue_bind(
                exchange="medical.reports",
                queue="doctor.radiology.reports",
                routing_key="report.examination.completed",
            )

            self.channel.queue_bind(
                exchange="medical.events",
                queue="doctor.radiology.reports",
                routing_key="doctor.report.ready",
            )

            track_dependency_status("rabbitmq", True)
            logger_service.info("Successfully connected to RabbitMQ")

        except Exception as e:
            track_dependency_status("rabbitmq", False)
            track_circuit_breaker_failure("rabbitmq")
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
                    headers={"service": "medecins-service"},
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

    def notify_appointment_response(
        self, appointment_id: str, doctor_id: str, status: str, message: str = None
    ):
        """Notify about appointment response"""
        payload = {
            "appointment_id": appointment_id,
            "doctor_id": doctor_id,
            "status": status,
            "message": message,
            "timestamp": time.time(),
        }

        return self.publish_message(
            exchange="medical.appointments",
            routing_key=f"appointment.response.{status}",
            message=payload,
        )

    def notify_prescription_created(
        self, prescription_id: str, doctor_id: str, patient_id: str
    ):
        """Notify when a new prescription has been created"""
        payload = {
            "prescription_id": prescription_id,
            "doctor_id": doctor_id,
            "patient_id": patient_id,
            "status": "created",
            "timestamp": time.time(),
        }

        return self.publish_message(
            exchange="medical.prescriptions",
            routing_key="prescription.created",
            message=payload,
        )

    def request_radiology_examination(
        self,
        request_id: str,
        doctor_id: str,
        patient_id: str,
        patient_name: str,
        exam_type: str,
        reason: Optional[str] = None,
        urgency: str = "normal",
    ):
        """Request a radiology examination for a patient"""
        payload = {
            "request_id": request_id,
            "doctor_id": doctor_id,
            "patient_id": patient_id,
            "patient_name": patient_name,
            "exam_type": exam_type,
            "reason": reason,
            "urgency": urgency,
            "status": "requested",
            "timestamp": time.time(),
        }

        return self.publish_message(
            exchange="medical.reports",
            routing_key="report.examination.requested",
            message=payload,
        )

    def notify_patient_medical_update(
        self, patient_id: str, update_type: str, data: Dict[str, Any]
    ):
        """Send a medical update for a patient"""
        payload = {
            "patient_id": patient_id,
            "update_type": update_type,
            "data": data,
            "timestamp": time.time(),
        }

        return self.publish_message(
            exchange="medical.events",
            routing_key=f"patient.medical_update.{update_type}",
            message=payload,
        )

    def close(self):
        """Close the RabbitMQ connection"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
            logger_service.info("RabbitMQ connection closed")
