import functools
import time

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from services.logger_service import logger_service

# Initialize OpenTelemetry meter provider
meter_provider = MeterProvider()
metrics.set_meter_provider(meter_provider)


# Get a meter (equivalent to a registry in Prometheus)
meter = metrics.get_meter("patients_service")

# RabbitMQ metrics
RABBITMQ_MESSAGES_PUBLISHED = meter.create_counter(
    name="patients_service_rabbitmq_messages_published_total",
    description="Total number of messages published by patients service",
)

RABBITMQ_PUBLISH_LATENCY = meter.create_histogram(
    name="patients_service_rabbitmq_publish_latency_seconds",
    description="Message publish latency in seconds for patients service",
)

RABBITMQ_CONSUME_LATENCY = meter.create_histogram(
    name="patients_service_rabbitmq_consume_latency_seconds",
    description="Message consume latency in seconds for patients service",
)

RABBITMQ_QUEUE_SIZE = meter.create_up_down_counter(
    name="patients_service_rabbitmq_queue_size",
    description="Number of messages in queue for patients service",
)

RABBITMQ_CONSUMER_COUNT = meter.create_up_down_counter(
    name="patients_service_rabbitmq_consumers",
    description="Number of consumers for patients service",
)

# Circuit breaker metrics
CIRCUIT_BREAKER_STATE = meter.create_up_down_counter(
    name="patients_service_circuit_breaker_state",
    description="Circuit breaker state (0=closed, 1=open, 2=half-open) for patients service",
)

CIRCUIT_BREAKER_FAILURES = meter.create_counter(
    name="patients_service_circuit_breaker_failures_total",
    description="Number of circuit breaker failures for patients service",
)

CIRCUIT_BREAKER_SUCCESS = meter.create_counter(
    name="patients_service_circuit_breaker_success_total",
    description="Number of circuit breaker successes for patients service",
)

CIRCUIT_BREAKER_REJECTED = meter.create_counter(
    name="patients_service_circuit_breaker_rejected_total",
    description="Number of requests rejected due to open circuit for patients service",
)

# Cache metrics
CACHE_HITS = meter.create_counter(
    name="patients_service_cache_hits_total",
    description="Number of cache hits for patients service",
)

CACHE_MISSES = meter.create_counter(
    name="patients_service_cache_misses_total",
    description="Number of cache misses for patients service",
)

# Service dependency metrics
SERVICE_DEPENDENCY_UP = meter.create_up_down_counter(
    name="patients_service_dependency_up",
    description="Whether a service dependency is available (1=up, 0=down) for patients service",
)

SERVICE_DEPENDENCY_LATENCY = meter.create_histogram(
    name="patients_service_dependency_latency_seconds",
    description="Service dependency request latency in seconds for patients service",
)


def track_rabbitmq_metrics(func):
    """Decorator to track RabbitMQ operation metrics"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Get exchange and routing key from args/kwargs based on the function
        exchange = kwargs.get("exchange", "default")
        routing_key = kwargs.get("routing_key", "default")
        queue = kwargs.get("queue", "default")

        start_time = time.time()
        try:
            result = func(*args, **kwargs)

            # Record metrics based on operation type
            if func.__name__ == "publish":
                RABBITMQ_MESSAGES_PUBLISHED.add(
                    1, {"exchange": exchange, "routing_key": routing_key}
                )
                RABBITMQ_PUBLISH_LATENCY.record(
                    time.time() - start_time,
                    {"exchange": exchange, "routing_key": routing_key},
                )
            elif func.__name__ == "basic_consume":
                RABBITMQ_CONSUME_LATENCY.record(
                    time.time() - start_time, {"queue": queue}
                )

            return result
        except Exception as e:
            # Log the error but don't prevent it from propagating
            logger_service.exception(f"Error in RabbitMQ operation: {str(e)}")
            raise

    return wrapper


def update_queue_metrics(channel, queue_name):
    """Update queue-related metrics"""
    try:
        # Get queue statistics
        queue = channel.queue_declare(queue=queue_name, passive=True)
        message_count = queue.method.message_count
        consumer_count = queue.method.consumer_count

        # Update OpenTelemetry metrics
        RABBITMQ_QUEUE_SIZE.add(
            message_count - RABBITMQ_QUEUE_SIZE.get_value(), {"queue": queue_name}
        )
        RABBITMQ_CONSUMER_COUNT.add(
            consumer_count - RABBITMQ_CONSUMER_COUNT.get_value(), {"queue": queue_name}
        )
    except Exception as e:
        # Log but don't fail if we can't get metrics
        logger_service.warning(f"Error updating queue metrics: {str(e)}")


def track_circuit_breaker_state(name: str, state: str):
    """Update circuit breaker state metric"""
    state_values = {"closed": 0, "open": 1, "half_open": 2}
    try:
        # Remove old value and set the new one
        current_value = CIRCUIT_BREAKER_STATE.get_value({"name": name})
        new_value = state_values.get(state, 0)
        CIRCUIT_BREAKER_STATE.add(new_value - current_value, {"name": name})
        logger_service.debug(f"Circuit breaker '{name}' state changed to {state}")
    except Exception as e:
        logger_service.warning(f"Error tracking circuit breaker state: {str(e)}")


def track_circuit_breaker_failure(name: str):
    """Increment circuit breaker failure counter"""
    try:
        CIRCUIT_BREAKER_FAILURES.add(1, {"name": name})
    except Exception as e:
        logger_service.warning(f"Error tracking circuit breaker failure: {str(e)}")


def track_circuit_breaker_success(name: str):
    """Increment circuit breaker success counter"""
    try:
        CIRCUIT_BREAKER_SUCCESS.add(1, {"name": name})
    except Exception as e:
        logger_service.warning(f"Error tracking circuit breaker success: {str(e)}")


def track_circuit_breaker_rejection(name: str):
    """Increment circuit breaker rejection counter"""
    try:
        CIRCUIT_BREAKER_REJECTED.add(1, {"name": name})
    except Exception as e:
        logger_service.warning(f"Error tracking circuit breaker rejection: {str(e)}")


def track_cache_metrics(hit: bool, cache_name: str):
    """Track cache hit/miss metrics"""
    try:
        if hit:
            CACHE_HITS.add(1, {"cache": cache_name})
        else:
            CACHE_MISSES.add(1, {"cache": cache_name})
    except Exception as e:
        logger_service.warning(f"Error tracking cache metrics: {str(e)}")


def track_dependency_status(service: str, is_available: bool):
    """Track service dependency availability"""
    try:
        current_value = SERVICE_DEPENDENCY_UP.get_value({"service": service})
        new_value = 1 if is_available else 0
        SERVICE_DEPENDENCY_UP.add(new_value - current_value, {"service": service})
    except Exception as e:
        logger_service.warning(
            f"Error tracking dependency status for {service}: {str(e)}"
        )


def track_dependency_request(func):
    """Decorator to track service dependency request metrics"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        service = kwargs.get("service", func.__name__)
        operation = kwargs.get("operation", "request")

        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            # Record successful dependency call
            track_dependency_status(service, True)
            SERVICE_DEPENDENCY_LATENCY.record(
                time.time() - start_time, {"service": service, "operation": operation}
            )
            return result
        except Exception as e:
            # Record failed dependency call
            track_dependency_status(service, False)
            raise

    return wrapper
