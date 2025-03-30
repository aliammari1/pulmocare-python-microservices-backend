import json
import time
from datetime import datetime

import pika
from services.logger_service import logger_service
from services.metrics import (RABBITMQ_MESSAGES_PUBLISHED,
                              RABBITMQ_PUBLISH_LATENCY)


class RabbitMQClient:
    """RabbitMQ client service for message queue operations"""

    def __init__(self, config):
        self.config = config
        self.connection = None
        self.channel = None
        self._setup_connection()

    def _setup_connection(self):
        """Initialize RabbitMQ connection and channel"""
        try:
            # Create connection parameters
            credentials = pika.PlainCredentials(
                self.config.RABBITMQ_USER, self.config.RABBITMQ_PASS
            )

            parameters = pika.ConnectionParameters(
                host=self.config.RABBITMQ_HOST,
                port=self.config.RABBITMQ_PORT,
                virtual_host=self.config.RABBITMQ_VHOST,
                credentials=credentials,
                heartbeat=600,
            )

            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()

            # Declare exchanges
            self.channel.exchange_declare(
                exchange="medical.events", exchange_type="topic", durable=True
            )

            self.channel.exchange_declare(
                exchange="medical.reports", exchange_type="topic", durable=True
            )

            # Declare queues
            self.channel.queue_declare(queue="report.analysis", durable=True)

            self.channel.queue_declare(queue="report.notifications", durable=True)

            # Bind queues to exchanges
            self.channel.queue_bind(
                exchange="medical.reports",
                queue="report.analysis",
                routing_key="report.created",
            )

            self.channel.queue_bind(
                exchange="medical.reports",
                queue="report.notifications",
                routing_key="report.#",
            )

            logger_service.info("Successfully connected to RabbitMQ")

        except Exception as e:
            logger_service.error(f"Failed to connect to RabbitMQ: {str(e)}")
            raise

    def publish_message(self, exchange, routing_key, message, correlation_id=None):
        """Publish a message to RabbitMQ with metrics tracking"""
        try:
            if not self.connection or self.connection.is_closed:
                self._setup_connection()

            start_time = time.time()

            # Convert message to JSON if it's a dict
            if isinstance(message, dict):
                message = json.dumps(message)

            properties = pika.BasicProperties(
                delivery_mode=2,  # make message persistent
                content_type="application/json",
                correlation_id=correlation_id,
                timestamp=int(time.time()),
            )

            self.channel.basic_publish(
                exchange=exchange,
                routing_key=routing_key,
                body=message,
                properties=properties,
            )

            # Record metrics
            RABBITMQ_MESSAGES_PUBLISHED.labels(
                exchange=exchange, routing_key=routing_key
            ).inc()

            RABBITMQ_PUBLISH_LATENCY.labels(
                exchange=exchange, routing_key=routing_key
            ).observe(time.time() - start_time)

            logger_service.debug(f"Published message to {exchange}:{routing_key}")

        except Exception as e:
            logger_service.error(f"Failed to publish message: {str(e)}")
            raise

    def publish_report_created(self, report_id):
        """Publish report creation event"""
        message = {
            "event": "report_created",
            "report_id": str(report_id),
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.publish_message("medical.reports", "report.created", message)

    def publish_report_updated(self, report_id):
        """Publish report update event"""
        message = {
            "event": "report_updated",
            "report_id": str(report_id),
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.publish_message("medical.reports", "report.updated", message)

    def publish_report_deleted(self, report_id):
        """Publish report deletion event"""
        message = {
            "event": "report_deleted",
            "report_id": str(report_id),
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.publish_message("medical.reports", "report.deleted", message)

    def close(self):
        """Close RabbitMQ connection"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
