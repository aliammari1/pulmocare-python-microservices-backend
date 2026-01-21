import functools
import json
import socket
import time
from collections.abc import Callable
from typing import Any

import pika

from config import Config
from services.logger_service import logger_service
from services.metrics import (
    RABBITMQ_MESSAGES_PUBLISHED,
    RABBITMQ_PUBLISH_LATENCY,
    track_circuit_breaker_failure,
    track_dependency_status,
)


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
            credentials = pika.PlainCredentials(self.config.RABBITMQ_USER, self.config.RABBITMQ_PASS)
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
            self.channel.exchange_declare(exchange="medical.events", exchange_type="topic", durable=True)
            self.channel.exchange_declare(exchange="medical.commands", exchange_type="direct", durable=True)
            self.channel.exchange_declare(exchange="medical.appointments", exchange_type="topic", durable=True)
            self.channel.exchange_declare(exchange="medical.prescriptions", exchange_type="topic", durable=True)
            self.channel.exchange_declare(exchange="medical.reports", exchange_type="topic", durable=True)
            self.channel.exchange_declare(exchange="medical.notifications", exchange_type="topic", durable=True)

            # Declare queues for appointments service
            self.channel.queue_declare(queue="appointment.requests", durable=True)
            self.channel.queue_declare(queue="appointment.responses", durable=True)
            self.channel.queue_declare(queue="appointment.notifications", durable=True)
            self.channel.queue_declare(queue="patient.notifications", durable=True)
            self.channel.queue_declare(queue="doctor.notifications", durable=True)
            self.channel.queue_declare(queue="appointment.status.updates", durable=True)
            self.channel.queue_declare(queue="provider.schedule.updates", durable=True)

            # Bind queues to exchanges with appropriate routing keys
            self.channel.queue_bind(
                exchange="medical.appointments",
                queue="appointment.requests",
                routing_key="appointment.request.#",
            )

            self.channel.queue_bind(
                exchange="medical.appointments",
                queue="appointment.responses",
                routing_key="appointment.response.#",
            )

            self.channel.queue_bind(
                exchange="medical.appointments",
                queue="appointment.status.updates",
                routing_key="appointment.status.#",
            )

            self.channel.queue_bind(
                exchange="medical.appointments",
                queue="provider.schedule.updates",
                routing_key="provider.schedule.#",
            )

            self.channel.queue_bind(
                exchange="medical.notifications",
                queue="patient.notifications",
                routing_key="notification.patient.#",
            )

            self.channel.queue_bind(
                exchange="medical.notifications",
                queue="doctor.notifications",
                routing_key="notification.doctor.#",
            )

            self.channel.queue_bind(
                exchange="medical.notifications",
                queue="appointment.notifications",
                routing_key="notification.appointment.#",
            )

            track_dependency_status("rabbitmq", True)
            logger_service.info("Successfully connected to RabbitMQ")

        except Exception as e:
            track_dependency_status("rabbitmq", False)
            track_circuit_breaker_failure("rabbitmq")
            logger_service.error(f"Failed to connect to RabbitMQ: {e!s}")

    @track_rabbitmq_metrics
    def publish_message(self, exchange: str, routing_key: str, message: dict[str, Any]):
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
                    headers={"service": self.config.SERVICE_NAME},
                ),
            )

            logger_service.info(f"Published message to {exchange}:{routing_key}")
            return True

        except Exception as e:
            logger_service.error(f"Failed to publish message: {e!s}")
            return False

    def consume_messages(self, queue_name: str, callback: Callable):
        """Set up a consumer for the specified queue"""
        if not self.connection or self.connection.is_closed:
            self._setup_connection()

        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(queue=queue_name, on_message_callback=callback)
        logger_service.info(f"Started consuming messages from {queue_name}")

    def notify_appointment_created(self, appointment_data: dict[str, Any]):
        """Notify about a new appointment being created"""
        return self.publish_message(
            exchange="medical.appointments",
            routing_key="appointment.created",
            message=appointment_data,
        )

    def notify_appointment_updated(self, appointment_data: dict[str, Any], update_type: str = "general"):
        """Notify about an appointment being updated"""
        return self.publish_message(
            exchange="medical.appointments",
            routing_key=f"appointment.updated.{update_type}",
            message=appointment_data,
        )

    def notify_appointment_cancelled(self, appointment_data: dict[str, Any], reason: str | None = None):
        """Notify about an appointment being cancelled"""
        message = appointment_data.copy()
        if reason:
            message["cancellation_reason"] = reason

        return self.publish_message(
            exchange="medical.appointments",
            routing_key="appointment.cancelled",
            message=message,
        )

    def notify_appointment_status_change(self, appointment_id: str, status: str, provider_id: str, patient_id: str):
        """Notify about an appointment status change"""
        payload = {
            "appointment_id": appointment_id,
            "status": status,
            "provider_id": provider_id,
            "patient_id": patient_id,
            "timestamp": time.time(),
        }

        return self.publish_message(
            exchange="medical.appointments",
            routing_key=f"appointment.status.{status}",
            message=payload,
        )

    def send_appointment_reminder(
        self,
        appointment_id: str,
        recipient_id: str,
        recipient_type: str,
        appointment_time: str,
        provider_name: str,
    ):
        """Send a reminder about an upcoming appointment"""
        payload = {
            "appointment_id": appointment_id,
            "recipient_id": recipient_id,
            "recipient_type": recipient_type,
            "appointment_time": appointment_time,
            "provider_name": provider_name,
            "notification_type": "appointment_reminder",
            "timestamp": time.time(),
        }

        return self.publish_message(
            exchange="medical.notifications",
            routing_key=f"notification.{recipient_type}.appointment_reminder",
            message=payload,
        )

    def notify_provider_schedule_update(self, provider_id: str, provider_type: str):
        """Notify about a provider's schedule being updated"""
        payload = {
            "provider_id": provider_id,
            "provider_type": provider_type,
            "timestamp": time.time(),
        }

        return self.publish_message(
            exchange="medical.appointments",
            routing_key="provider.schedule.updated",
            message=payload,
        )

    def notify_appointment_response(
        self,
        appointment_id: str,
        doctor_id: str,
        patient_id: str,
        status: str,
        message: str = None,
    ):
        """Notify about appointment response (accept/reject)"""
        payload = {
            "appointment_id": appointment_id,
            "doctor_id": doctor_id,
            "patient_id": patient_id,
            "status": status,
            "message": message,
            "timestamp": time.time(),
        }

        return self.publish_message(
            exchange="medical.appointments",
            routing_key=f"appointment.response.{status}",
            message=payload,
        )

    def notify_prescription_created(self, prescription_id: str, doctor_id: str, patient_id: str):
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
        reason: str | None = None,
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

    def notify_patient_medical_update(self, patient_id: str, update_type: str, data: dict[str, Any]):
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
