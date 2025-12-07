import json
import os
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.exchange_type import ExchangeType
from services.logger_service import logger_service


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
        self.service_name = "patients"  # Name of this service for routing keys

        # Define exchange names for different domains
        self.exchanges = {
            "medical": "medical.exchange",
            "appointments": "medical.appointments",
            "notifications": "notifications.exchange",
            "patient": "patient.events",
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

    def publish_message(
            self, exchange: str, routing_key: str, message: Dict[str, Any]
    ) -> bool:
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

            logger_service.info(
                f"Published message to exchange={exchange}, routing_key={routing_key}"
            )
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

                logger_service.info(
                    f"Successfully republished message after reconnect to {exchange}, routing_key={routing_key}"
                )
                return True
            except Exception as retry_error:
                logger_service.error(
                    f"Failed to republish message after reconnect: {retry_error}"
                )
                return False

    def publish_patient_update(
            self, patient_id: str, update_type: str, data: Dict[str, Any]
    ) -> bool:
        """
        Publish a patient update message.

        Args:
            patient_id: ID of the patient
            update_type: Type of update (created, updated, medical_history_added, etc.)
            data: Update data

        Returns:
            bool: True if successful, False otherwise
        """
        message = {
            "patient_id": patient_id,
            "update_type": update_type,
            "data": data,
            "service": self.service_name,
        }

        # Publish to the patient exchange
        return self.publish_message(
            exchange=self.exchanges["patient"],
            routing_key=f"patient.{update_type}",
            message=message,
        )

    def publish_appointment_request(
            self, patient_id: str, doctor_id: str, appointment_data: Dict
    ) -> bool:
        """
        Publish an appointment request message.

        Args:
            patient_id: ID of the patient
            doctor_id: ID of the doctor
            appointment_data: Appointment details

        Returns:
            bool: True if successful, False otherwise
        """
        message = {
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "appointment_data": appointment_data,
            "service": self.service_name,
        }

        # Publish to the appointments exchange
        return self.publish_message(
            exchange=self.exchanges["appointments"],
            routing_key="appointment.request.created",
            message=message,
        )

    def setup_patient_notifications_consumer(self, callback) -> None:
        """
        Setup a consumer for patient notifications.

        Args:
            callback: Function to call when a message is received
        """
        channel = self._get_channel()

        # Declare a queue for this service to receive patient notifications
        result = channel.queue_declare(
            queue=f"{self.service_name}.patient.notifications",
            durable=True,
            exclusive=False,
            auto_delete=False,
        )
        queue_name = result.method.queue

        # Bind the queue to relevant routing keys
        channel.queue_bind(
            exchange=self.exchanges["notifications"],
            queue=queue_name,
            routing_key="notification.patient.*",
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

    def setup_appointment_status_consumer(self, callback) -> None:
        """
        Setup a consumer for appointment status updates.

        Args:
            callback: Function to call when a message is received
        """
        channel = self._get_channel()

        # Declare a queue for this service to receive appointment status updates
        result = channel.queue_declare(
            queue=f"{self.service_name}.appointment.status",
            durable=True,
            exclusive=False,
            auto_delete=False,
        )
        queue_name = result.method.queue

        # Bind the queue to relevant routing keys
        channel.queue_bind(
            exchange=self.exchanges["appointments"],
            queue=queue_name,
            routing_key="appointment.status.*",
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
        channel.start_consuming()

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
            logger_service.debug(
                f"Rejected message with tag {delivery_tag}, requeue={requeue}"
            )

    def request_patient_prescriptions(
            self, patient_id: str, timeout: int = 10
    ) -> List[Dict]:
        """
        Request patient prescriptions from ordonnances service using RabbitMQ.

        Args:
            patient_id: ID of the patient
            timeout: Timeout in seconds for response

        Returns:
            List of prescription dictionaries
        """
        return self._request_patient_data(
            patient_id=patient_id, data_type="prescriptions", timeout=timeout
        )

    def request_patient_medical_records(
            self, patient_id: str, timeout: int = 10
    ) -> List[Dict]:
        """
        Request patient medical records from medecins service using RabbitMQ.

        Args:
            patient_id: ID of the patient
            timeout: Timeout in seconds for response

        Returns:
            List of medical record dictionaries
        """
        return self._request_patient_data(
            patient_id=patient_id, data_type="medical_records", timeout=timeout
        )

    def request_patient_radiology_reports(
            self, patient_id: str, timeout: int = 10
    ) -> List[Dict]:
        """
        Request patient radiology reports from radiologues service using RabbitMQ.

        Args:
            patient_id: ID of the patient
            timeout: Timeout in seconds for response

        Returns:
            List of radiology report dictionaries
        """
        return self._request_patient_data(
            patient_id=patient_id, data_type="radiology_reports", timeout=timeout
        )

    def _request_patient_data(
            self, patient_id: str, data_type: str, timeout: int = 10
    ) -> List[Dict]:
        """
        Generic method to request patient data from other services.

        Args:
            patient_id: ID of the patient
            data_type: Type of data to request (prescriptions, medical_records, radiology_reports)
            timeout: Timeout in seconds for response

        Returns:
            List of data dictionaries
        """
        try:
            # Generate a correlation ID for this request
            correlation_id = f"{uuid.uuid4()}"

            # Determine the target exchange and routing key based on data_type
            if data_type == "prescriptions":
                exchange = self.exchanges["medical"]
                routing_key = "patient.data.prescriptions.request"
            elif data_type == "medical_records":
                exchange = self.exchanges["medical"]
                routing_key = "patient.data.medical_records.request"
            elif data_type == "radiology_reports":
                exchange = self.exchanges["medical"]
                routing_key = "patient.data.radiology_reports.request"
            else:
                raise ValueError(f"Unsupported data type: {data_type}")

            # Create a response queue with a unique name
            channel = self._get_channel()
            response_queue = channel.queue_declare(
                queue="", exclusive=True, auto_delete=True
            )
            response_queue_name = response_queue.method.queue

            # Store for the response
            response_data = None
            response_received = threading.Event()

            # Define the callback to handle the response
            def on_response(ch, method, properties, body):
                nonlocal response_data
                if properties.correlation_id == correlation_id:
                    try:
                        response_data = json.loads(body)
                        response_received.set()
                    except json.JSONDecodeError as e:
                        logger_service.error(f"Failed to decode response: {e}")
                    finally:
                        ch.basic_ack(delivery_tag=method.delivery_tag)

            # Start consuming from the response queue
            channel.basic_consume(
                queue=response_queue_name,
                on_message_callback=on_response,
                auto_ack=False,
            )

            # Publish the request message
            request_message = {
                "patient_id": patient_id,
                "service": self.service_name,
                "request_time": datetime.utcnow().isoformat(),
            }

            properties = pika.BasicProperties(
                reply_to=response_queue_name,
                correlation_id=correlation_id,
                content_type="application/json",
                delivery_mode=2,  # make message persistent
            )

            channel.basic_publish(
                exchange=exchange,
                routing_key=routing_key,
                body=json.dumps(request_message),
                properties=properties,
            )

            logger_service.info(
                f"Sent request for {data_type} with correlation ID {correlation_id}"
            )

            # Start a thread to consume responses (non-blocking)
            consume_thread = threading.Thread(
                target=lambda: channel.start_consuming(), daemon=True
            )
            consume_thread.start()

            # Wait for the response with timeout
            response_received.wait(timeout)

            # Stop consuming
            if channel.is_open:
                channel.stop_consuming()

            # Check if we got a response
            if not response_received.is_set():
                logger_service.warning(f"Timeout waiting for {data_type} response")
                return []

            if response_data is None:
                return []

            # Return the data from the response
            return response_data.get("data", [])

        except Exception as e:
            logger_service.error(f"Error requesting {data_type}: {e}")
            return []
