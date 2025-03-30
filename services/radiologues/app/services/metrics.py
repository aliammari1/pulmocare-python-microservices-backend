import functools
import time

from prometheus_client import Counter, Gauge, Histogram
from services.logger_service import logger_service

# RabbitMQ metrics
RABBITMQ_MESSAGES_PUBLISHED = Counter(
    "radiologues_service_rabbitmq_messages_published_total",
    "Total number of messages published by radiologues service",
    ["exchange", "routing_key"],
)

RABBITMQ_PUBLISH_LATENCY = Histogram(
    "radiologues_service_rabbitmq_publish_latency_seconds",
    "Message publish latency in seconds for radiologues service",
    ["exchange", "routing_key"],
)

RABBITMQ_CONSUME_LATENCY = Histogram(
    "radiologues_service_rabbitmq_consume_latency_seconds",
    "Message consume latency in seconds for radiologues service",
    ["queue"],
)

RABBITMQ_QUEUE_SIZE = Gauge(
    "radiologues_service_rabbitmq_queue_size",
    "Number of messages in queue for radiologues service",
    ["queue"],
)

RABBITMQ_CONSUMER_COUNT = Gauge(
    "radiologues_service_rabbitmq_consumers",
    "Number of consumers for radiologues service",
    ["queue"],
)

# Circuit breaker metrics
CIRCUIT_BREAKER_STATE = Gauge(
    "radiologues_service_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half-open) for radiologues service",
    ["name"],
)

CIRCUIT_BREAKER_FAILURES = Counter(
    "radiologues_service_circuit_breaker_failures_total",
    "Number of circuit breaker failures for radiologues service",
    ["name"],
)

CIRCUIT_BREAKER_SUCCESS = Counter(
    "radiologues_service_circuit_breaker_success_total",
    "Number of circuit breaker successes for radiologues service",
    ["name"],
)

CIRCUIT_BREAKER_REJECTED = Counter(
    "radiologues_service_circuit_breaker_rejected_total",
    "Number of requests rejected due to open circuit for radiologues service",
    ["name"],
)

# Cache metrics
CACHE_HITS = Counter(
    "radiologues_service_cache_hits_total",
    "Number of cache hits for radiologues service",
    ["cache"],
)

CACHE_MISSES = Counter(
    "radiologues_service_cache_misses_total",
    "Number of cache misses for radiologues service",
    ["cache"],
)

# Service dependency metrics
SERVICE_DEPENDENCY_UP = Gauge(
    "radiologues_service_dependency_up",
    "Whether a service dependency is available (1=up, 0=down) for radiologues service",
    ["service"],
)

SERVICE_DEPENDENCY_LATENCY = Histogram(
    "radiologues_service_dependency_latency_seconds",
    "Service dependency request latency in seconds for radiologues service",
    ["service", "operation"],
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
                RABBITMQ_MESSAGES_PUBLISHED.labels(
                    exchange=exchange, routing_key=routing_key
                ).inc()
                RABBITMQ_PUBLISH_LATENCY.labels(
                    exchange=exchange, routing_key=routing_key
                ).observe(time.time() - start_time)
            elif func.__name__ == "basic_consume":
                RABBITMQ_CONSUME_LATENCY.labels(queue=queue).observe(
                    time.time() - start_time
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

        # Update Prometheus metrics
        RABBITMQ_QUEUE_SIZE.labels(queue=queue_name).set(message_count)
        RABBITMQ_CONSUMER_COUNT.labels(queue=queue_name).set(consumer_count)
    except Exception as e:
        # Log but don't fail if we can't get metrics
        logger_service.warning(f"Error updating queue metrics: {str(e)}")


def track_circuit_breaker_state(name: str, state: str):
    """Update circuit breaker state metric"""
    state_values = {"closed": 0, "open": 1, "half_open": 2}
    try:
        CIRCUIT_BREAKER_STATE.labels(name=name).set(state_values.get(state, 0))
        logger_service.debug(f"Circuit breaker '{name}' state changed to {state}")
    except Exception as e:
        logger_service.warning(f"Error tracking circuit breaker state: {str(e)}")


def track_circuit_breaker_failure(name: str):
    """Increment circuit breaker failure counter"""
    try:
        CIRCUIT_BREAKER_FAILURES.labels(name=name).inc()
    except Exception as e:
        logger_service.warning(f"Error tracking circuit breaker failure: {str(e)}")


def track_circuit_breaker_success(name: str):
    """Increment circuit breaker success counter"""
    try:
        CIRCUIT_BREAKER_SUCCESS.labels(name=name).inc()
    except Exception as e:
        logger_service.warning(f"Error tracking circuit breaker success: {str(e)}")


def track_circuit_breaker_rejection(name: str):
    """Increment circuit breaker rejection counter"""
    try:
        CIRCUIT_BREAKER_REJECTED.labels(name=name).inc()
    except Exception as e:
        logger_service.warning(f"Error tracking circuit breaker rejection: {str(e)}")


def track_cache_metrics(hit: bool, cache_name: str):
    """Track cache hit/miss metrics"""
    try:
        if hit:
            CACHE_HITS.labels(cache=cache_name).inc()
        else:
            CACHE_MISSES.labels(cache=cache_name).inc()
    except Exception as e:
        logger_service.warning(f"Error tracking cache metrics: {str(e)}")


def track_dependency_status(service: str, is_available: bool):
    """Track service dependency availability"""
    try:
        SERVICE_DEPENDENCY_UP.labels(service=service).set(1 if is_available else 0)
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
            SERVICE_DEPENDENCY_LATENCY.labels(
                service=service, operation=operation
            ).observe(time.time() - start_time)
            return result
        except Exception as e:
            # Record failed dependency call
            track_dependency_status(service, False)
            raise

    return wrapper
