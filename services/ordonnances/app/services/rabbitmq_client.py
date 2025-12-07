import json
import socket
import time
from typing import Any, Callable, Dict, Optional

import pika
from services.logger_service import logger_service
from services.metrics import RABBITMQ_MESSAGES_PUBLISHED, RABBITMQ_PUBLISH_LATENCY

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
                exchange="medical.prescriptions", exchange_type="topic", durable=True
            )

            # Declare queues for ordonnances service
            self.channel.queue_declare(queue="ordonnances.created", durable=True)
            self.channel.queue_declare(queue="ordonnances.notifications", durable=True)
            self.channel.queue_declare(queue="patient.prescriptions", durable=True)
            self.channel.queue_declare(queue="doctor.prescriptions", durable=True)

            # Bind queues to exchanges with appropriate routing keys
            self.channel.queue_bind(
                exchange="medical.prescriptions",
                queue="ordonnances.created",
                routing_key="prescription.created",
            )

            self.channel.queue_bind(
                exchange="medical.events",
                queue="ordonnances.notifications",
                routing_key="prescription.#",
            )

            self.channel.queue_bind(
                exchange="medical.prescriptions",
                queue="patient.prescriptions",
                routing_key="prescription.patient.*",
            )

            self.channel.queue_bind(
                exchange="medical.prescriptions",
                queue="doctor.prescriptions",
                routing_key="prescription.doctor.*",
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
                    headers={"service": "ordonnances-service"},
                ),
            )

            # Record metrics
            RABBITMQ_MESSAGES_PUBLISHED.labels(
                exchange=exchange, routing_key=routing_key
            ).inc()

            RABBITMQ_PUBLISH_LATENCY.labels(
                exchange=exchange, routing_key=routing_key
            ).observe(time.time() - start_time)

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

    def notify_prescription_created(
            self, prescription_id: str, doctor_id: str, patient_id: str
    ):
        """Notify when a new prescription has been created"""
        payload = {
            "prescription_id": prescription_id,
            "doctor_id": doctor_id,
            "patient_id": patient_id,
            "event": "prescription_created",
            "timestamp": time.time(),
        }

        # Publish to medical.events for general notifications
        self.publish_message(
            exchange="medical.events",
            routing_key="prescription.created",
            message=payload,
        )

        # Also publish to medical.prescriptions for more specific routing
        return self.publish_message(
            exchange="medical.prescriptions",
            routing_key="prescription.created",
            message=payload,
        )

    def notify_prescription_dispensed(
            self, prescription_id: str, pharmacy_id: Optional[str] = None
    ):
        """Notify when a prescription has been dispensed"""
        payload = {
            "prescription_id": prescription_id,
            "pharmacy_id": pharmacy_id,
            "event": "prescription_dispensed",
            "timestamp": time.time(),
        }

        return self.publish_message(
            exchange="medical.prescriptions",
            routing_key="prescription.dispensed",
            message=payload,
        )

    def notify_patient_prescription(
            self, prescription_id: str, patient_id: str, action: str
    ):
        """Send prescription notification to patient"""
        payload = {
            "prescription_id": prescription_id,
            "patient_id": patient_id,
            "action": action,
            "timestamp": time.time(),
        }

        return self.publish_message(
            exchange="medical.prescriptions",
            routing_key=f"prescription.patient.{action}",
            message=payload,
        )

    def notify_doctor_prescription(
            self, prescription_id: str, doctor_id: str, action: str
    ):
        """Send prescription notification to doctor"""
        payload = {
            "prescription_id": prescription_id,
            "doctor_id": doctor_id,
            "action": action,
            "timestamp": time.time(),
        }

        return self.publish_message(
            exchange="medical.prescriptions",
            routing_key=f"prescription.doctor.{action}",
            message=payload,
        )

    def close(self):
        """Close the RabbitMQ connection"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
            logger_service.info("RabbitMQ connection closed")
