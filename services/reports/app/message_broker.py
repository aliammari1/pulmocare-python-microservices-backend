import json
import socket
import time
from typing import Any, Dict

import pika

from circuit_breaker import CircuitBreaker
from services.logger_service import logger_service
from services.metrics import (
    track_dependency_status,
    track_rabbitmq_metrics,
    update_queue_metrics,
)


class MessageBroker:
    """Message broker with circuit breaker for RabbitMQ operations"""

    def __init__(self, config):
        """Initialize the message broker with circuit breaker"""
        self.config = config
        self.connection = None
        self.channel = None
        # Initialize circuit breaker for RabbitMQ operations
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=config.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout=config.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
            name="rabbitmq",
        )
        self._setup_connection()

    def _setup_connection(self):
        """Set up connection to RabbitMQ"""
        try:
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

            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()

            # Declare exchanges for inter-service communication
            self.channel.exchange_declare(
                exchange="medical.events", exchange_type="topic", durable=True
            )

            self.channel.exchange_declare(
                exchange="medical.commands", exchange_type="direct", durable=True
            )

            self.channel.exchange_declare(
                exchange="medical.reports", exchange_type="topic", durable=True
            )

            # Declare queues for reports service
            self.channel.queue_declare(queue="reports.processing", durable=True)
            self.channel.queue_declare(queue="reports.notifications", durable=True)
            self.channel.queue_declare(queue="reports.analysis", durable=True)

            # Bind queues to exchanges with appropriate routing keys
            self.channel.queue_bind(
                exchange="medical.events",
                queue="reports.processing",
                routing_key="report.created",
            )

            self.channel.queue_bind(
                exchange="medical.reports",
                queue="reports.analysis",
                routing_key="report.analysis.requested",
            )

            self.channel.queue_bind(
                exchange="medical.reports",
                queue="reports.notifications",
                routing_key="report.#",
            )

            logger_service.info("Successfully connected to RabbitMQ")

        except Exception as e:
            logger_service.error(f"Failed to connect to RabbitMQ: {str(e)}")
            if not self.config.RABBITMQ_IGNORE_CONNECTION_ERRORS:
                raise

    @track_rabbitmq_metrics
    def publish_message(self, exchange: str, routing_key: str, message: Dict[str, Any]):
        """Publish a message to RabbitMQ with circuit breaker protection"""
        try:

            def _publish():
                if not self.connection or self.connection.is_closed:
                    self._setup_connection()

                # Update metrics before publishing
                if self.channel:
                    try:
                        update_queue_metrics(self.channel, f"{exchange}.{routing_key}")
                    except Exception as metrics_error:
                        logger_service.warning(
                            f"Error updating metrics: {str(metrics_error)}"
                        )

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
                    ),
                )

                logger_service.info(f"Published message to {exchange}:{routing_key}")
                track_dependency_status("rabbitmq", True)
                return True

            # Use circuit breaker to protect against RabbitMQ failures
            return self.circuit_breaker.call(_publish)

        except Exception as e:
            logger_service.error(f"Failed to publish message: {str(e)}")
            track_dependency_status("rabbitmq", False)
            raise

    def consume_messages(self, queue_name: str, callback):
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

    def close(self):
        """Close the RabbitMQ connection"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
            logger_service.info("RabbitMQ connection closed")
