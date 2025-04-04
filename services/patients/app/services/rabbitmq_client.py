import json
import socket
import time
from typing import Any, Callable, Dict, Optional

import pika
from services.logger_service import logger_service

from config import Config


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

            # Declare queues for patients service
            self.channel.queue_declare(queue="patients.notifications", durable=True)
            self.channel.queue_declare(queue="patients.medical_updates", durable=True)
            self.channel.queue_declare(queue="patients.appointments", durable=True)
            self.channel.queue_declare(queue="patients.prescriptions", durable=True)

            # Bind queues to exchanges with appropriate routing keys
            self.channel.queue_bind(
                exchange="medical.events",
                queue="patients.notifications",
                routing_key="patient.notification.#",
            )

            self.channel.queue_bind(
                exchange="medical.events",
                queue="patients.medical_updates",
                routing_key="patient.medical_update.#",
            )

            self.channel.queue_bind(
                exchange="medical.appointments",
                queue="patients.appointments",
                routing_key="appointment.#",
            )

            self.channel.queue_bind(
                exchange="medical.prescriptions",
                queue="patients.prescriptions",
                routing_key="prescription.patient.#",
            )

            logger_service.info("Successfully connected to RabbitMQ")

        except Exception as e:
            logger_service.error(f"Failed to connect to RabbitMQ: {str(e)}")

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
                    headers={"service": "patients-service"},
                ),
            )

            logger_service.info(f"Published message to {exchange}:{routing_key}")
            return True

        except Exception as e:
            logger_service.error(f"Failed to publish message: {str(e)}")
            return False

    def consume_messages(self, queue_name: str, callback: Callable):
        """Set up a consumer for the specified queue"""
        try:
            if not self.connection or self.connection.is_closed:
                self._setup_connection()

            self.channel.basic_qos(prefetch_count=1)
            self.channel.basic_consume(queue=queue_name, on_message_callback=callback)

            logger_service.info(f"Started consuming messages from {queue_name}")
            self.channel.start_consuming()

        except Exception as e:
            logger_service.error(f"Error setting up consumer: {str(e)}")
            raise

    def request_appointment(
        self,
        patient_id: str,
        doctor_id: str,
        requested_time: str,
        reason: Optional[str] = None,
    ):
        """Request an appointment with a doctor"""
        appointment_id = f"apt-{int(time.time())}-{patient_id[:8]}-{doctor_id[:8]}"

        message = {
            "appointment_id": appointment_id,
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "requested_time": requested_time,
            "reason": reason,
            "status": "requested",
            "created_at": time.time(),
        }

        success = self.publish_message(
            exchange="medical.appointments",
            routing_key="appointment.created",
            message=message,
        )

        if success:
            return appointment_id
        return None

    def notify_patient_update(
        self, patient_id: str, update_type: str, data: Dict[str, Any]
    ):
        """Notify about a patient update"""
        message = {
            "patient_id": patient_id,
            "update_type": update_type,
            "data": data,
            "timestamp": time.time(),
        }

        return self.publish_message(
            exchange="medical.events",
            routing_key=f"patient.notification.{update_type}",
            message=message,
        )

    def report_medical_info(
        self, patient_id: str, info_type: str, data: Dict[str, Any]
    ):
        """Report patient medical information update"""
        message = {
            "patient_id": patient_id,
            "info_type": info_type,
            "data": data,
            "source": "patients-service",
            "timestamp": time.time(),
        }

        return self.publish_message(
            exchange="medical.events",
            routing_key=f"patient.medical_update.{info_type}",
            message=message,
        )

    def close(self):
        """Close the RabbitMQ connection"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
            logger_service.info("RabbitMQ connection closed")
