import json
import logging
import socket
import time
from typing import Any, Dict, Optional, Tuple

import pika
from circuit_breaker import CircuitBreaker
from metrics import (track_dependency_status, track_rabbitmq_metrics,
                     update_queue_metrics)

from config import Config

logger = logging.getLogger(__name__)


class MessageBroker:
    """Message broker with circuit breaker for RabbitMQ operations"""

    def __init__(self):
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[pika.channel.Channel] = None
        self.circuit = CircuitBreaker(
            name="rabbitmq",
            failure_threshold=Config.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout=Config.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
            expected_exception=pika.exceptions.AMQPError,
        )
        self._exchange_name = "medical.reports"
        self._queues = {
            "report.analysis": ["report.created"],
            "report.notifications": ["report.#"],
        }
        # Flag to indicate if we're in a development environment with connection errors ignored
        self._ignore_connection_errors = Config.RABBITMQ_IGNORE_CONNECTION_ERRORS

        # Set initial dependency status
        track_dependency_status("rabbitmq", False)

        logger.info(
            f"MessageBroker initialized with circuit breaker (ignore_errors={self._ignore_connection_errors})"
        )

    @property
    def connection(self) -> pika.BlockingConnection:
        """Get or create RabbitMQ connection"""
        if not self._connection or self._connection.is_closed:
            try:
                self._connection = self._create_connection()
                # Update dependency status to available
                track_dependency_status("rabbitmq", True)
            except Exception as e:
                # Update dependency status to unavailable
                track_dependency_status("rabbitmq", False)
                if self._ignore_connection_errors:
                    logger.warning(
                        f"Failed to connect to RabbitMQ but errors are ignored: {str(e)}"
                    )
                    return None
                raise
        return self._connection

    @property
    def channel(self) -> pika.channel.Channel:
        """Get or create RabbitMQ channel"""
        if not self._channel or self._channel.is_closed:
            conn = self.connection
            if conn:
                self._channel = conn.channel()
                self._declare_infrastructure()
        return self._channel

    @CircuitBreaker(name="rabbitmq_connection")
    def _create_connection(self) -> pika.BlockingConnection:
        """Create new RabbitMQ connection with retry logic"""
        max_retries = 5
        retry_delay = 1

        for attempt in range(max_retries):
            try:
                logger.info(
                    f"Attempting to connect to RabbitMQ at {Config.RABBITMQ_HOST}:{Config.RABBITMQ_PORT} (attempt {attempt+1}/{max_retries})"
                )
                credentials = pika.PlainCredentials(
                    Config.RABBITMQ_USER, Config.RABBITMQ_PASS
                )

                connection_params = pika.ConnectionParameters(
                    host=Config.RABBITMQ_HOST,
                    port=Config.RABBITMQ_PORT,
                    virtual_host=Config.RABBITMQ_VHOST,
                    credentials=credentials,
                    heartbeat=600,
                    connection_attempts=3,
                    socket_timeout=5,
                    retry_delay=1,
                    blocked_connection_timeout=300,
                )

                # Try to resolve hostname if it's not an IP
                if not self._is_ip_address(Config.RABBITMQ_HOST):
                    try:
                        resolved_ip = socket.gethostbyname(Config.RABBITMQ_HOST)
                        logger.info(f"Resolved {Config.RABBITMQ_HOST} to {resolved_ip}")
                    except socket.gaierror:
                        logger.warning(
                            f"Could not resolve hostname {Config.RABBITMQ_HOST}"
                        )
                        # In development mode, don't fail
                        if self._ignore_connection_errors:
                            raise pika.exceptions.AMQPConnectionError(
                                f"Could not resolve hostname {Config.RABBITMQ_HOST} (ignored in development)"
                            )
                        raise

                connection = pika.BlockingConnection(connection_params)
                logger.info("Successfully connected to RabbitMQ")
                return connection

            except pika.exceptions.AMQPError as e:
                if attempt == max_retries - 1:
                    logger.error(
                        f"Failed to connect to RabbitMQ after {max_retries} attempts"
                    )
                    raise

                logger.warning(
                    f"RabbitMQ connection attempt {attempt + 1} failed: {str(e)}"
                )
                time.sleep(retry_delay)
                retry_delay *= 2
            except Exception as e:
                logger.error(f"Unexpected error connecting to RabbitMQ: {str(e)}")
                if attempt == max_retries - 1:
                    raise
                time.sleep(retry_delay)
                retry_delay *= 2

    def _is_ip_address(self, host: str) -> bool:
        """Check if the host is an IP address"""
        try:
            socket.inet_aton(host)
            return True
        except socket.error:
            return False

    def _declare_infrastructure(self):
        """Declare exchanges, queues and bindings"""
        if not self._channel:
            logger.warning(
                "Cannot declare RabbitMQ infrastructure: no channel available"
            )
            return

        try:
            # Declare exchanges
            logger.info(f"Declaring exchange: {self._exchange_name}")
            self._channel.exchange_declare(
                exchange=self._exchange_name, exchange_type="topic", durable=True
            )

            # Declare queues and bindings
            for queue, routing_keys in self._queues.items():
                logger.info(f"Declaring queue: {queue}")
                self._channel.queue_declare(queue=queue, durable=True)

                for routing_key in routing_keys:
                    logger.info(
                        f"Binding queue {queue} to exchange {self._exchange_name} with routing key {routing_key}"
                    )
                    self._channel.queue_bind(
                        exchange=self._exchange_name,
                        queue=queue,
                        routing_key=routing_key,
                    )

            # Initialize queue metrics
            for queue in self._queues:
                update_queue_metrics(self._channel, queue)

            logger.info("Successfully declared RabbitMQ infrastructure")
        except Exception as e:
            logger.error(f"Error declaring RabbitMQ infrastructure: {str(e)}")
            if not self._ignore_connection_errors:
                raise

    @track_rabbitmq_metrics
    def publish(self, routing_key: str, message: dict, **properties):
        """Publish message with circuit breaker and metrics"""
        if not self._channel and self._ignore_connection_errors:
            logger.warning(
                f"Skipping message publish (routing_key={routing_key}): RabbitMQ connection not available"
            )
            return

        try:
            logger.info(
                f"Publishing message to {self._exchange_name} with routing key: {routing_key}"
            )
            logger.debug(f"Message content: {message}")

            self._channel.basic_publish(
                exchange=self._exchange_name,
                routing_key=routing_key,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # make message persistent
                    content_type="application/json",
                    **properties,
                ),
            )
            logger.info(
                f"Successfully published message with routing key: {routing_key}"
            )

            # Update queue metrics after publish
            for queue, routes in self._queues.items():
                for route in routes:
                    if self._routing_key_matches(route, routing_key):
                        update_queue_metrics(self._channel, queue)

        except pika.exceptions.AMQPError as e:
            logger.error(f"Failed to publish message: {str(e)}")
            if self._ignore_connection_errors:
                logger.warning("Message publishing error ignored in development mode")
            else:
                raise
        except Exception as e:
            logger.error(f"Unexpected error publishing message: {str(e)}")
            if not self._ignore_connection_errors:
                raise

    def _routing_key_matches(self, pattern: str, routing_key: str) -> bool:
        """Check if routing key matches pattern with wildcards"""
        if pattern == routing_key:
            return True
        if pattern.endswith("#"):
            prefix = pattern[:-1]
            return routing_key.startswith(prefix)
        if "#" not in pattern and "*" not in pattern:
            return False

        # For more complex patterns we'd need a more sophisticated matching algorithm
        # This is a simple implementation that handles the most common cases
        pattern_parts = pattern.split(".")
        key_parts = routing_key.split(".")

        if len(pattern_parts) > len(key_parts) and "#" not in pattern_parts:
            return False

        for i, part in enumerate(pattern_parts):
            if part == "#":
                return True
            if part == "*":
                if i >= len(key_parts):
                    return False
                continue
            if i >= len(key_parts) or part != key_parts[i]:
                return False

        return len(key_parts) == len(pattern_parts)

    def close(self):
        """Close RabbitMQ connection"""
        try:
            if self._connection and not self._connection.is_closed:
                self._connection.close()
                logger.info("Closed RabbitMQ connection")
        except Exception as e:
            logger.error(f"Error closing RabbitMQ connection: {str(e)}")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
