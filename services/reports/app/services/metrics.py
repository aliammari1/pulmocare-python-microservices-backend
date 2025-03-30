import functools
import time

from prometheus_client import Counter, Gauge, Histogram

# RabbitMQ metrics
RABBITMQ_MESSAGES_PUBLISHED = Counter(
    "reports_service_rabbitmq_messages_published_total",
    "Total number of messages published by reports service",
    ["exchange", "routing_key"],
)

RABBITMQ_PUBLISH_LATENCY = Histogram(
    "reports_service_rabbitmq_publish_latency_seconds",
    "Message publish latency in seconds for reports service",
    ["exchange", "routing_key"],
)

RABBITMQ_CONSUME_LATENCY = Histogram(
    "reports_service_rabbitmq_consume_latency_seconds",
    "Message consume latency in seconds for reports service",
    ["queue"],
)

RABBITMQ_QUEUE_SIZE = Gauge(
    "reports_service_rabbitmq_queue_size",
    "Number of messages in queue for reports service",
    ["queue"],
)

RABBITMQ_CONSUMER_COUNT = Gauge(
    "reports_service_rabbitmq_consumers",
    "Number of consumers for reports service",
    ["queue"],
)

# Circuit breaker metrics
CIRCUIT_BREAKER_STATE = Gauge(
    "reports_service_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half-open) for reports service",
    ["name"],
)

CIRCUIT_BREAKER_FAILURES = Counter(
    "reports_service_circuit_breaker_failures_total",
    "Number of circuit breaker failures for reports service",
    ["name"],
)

CIRCUIT_BREAKER_SUCCESS = Counter(
    "reports_service_circuit_breaker_success_total",
    "Number of circuit breaker successes for reports service",
    ["name"],
)

CIRCUIT_BREAKER_REJECTED = Counter(
    "reports_service_circuit_breaker_rejected_total",
    "Number of requests rejected due to open circuit for reports service",
    ["name"],
)

# Cache metrics
CACHE_HITS = Counter(
    "reports_service_cache_hits_total",
    "Number of cache hits for reports service",
    ["cache"],
)

CACHE_MISSES = Counter(
    "reports_service_cache_misses_total",
    "Number of cache misses for reports service",
    ["cache"],
)

# Service dependency metrics
SERVICE_DEPENDENCY_UP = Gauge(
    "reports_service_dependency_up",
    "Whether a service dependency is available (1=up, 0=down) for reports service",
    ["service"],
)

SERVICE_DEPENDENCY_LATENCY = Histogram(
    "reports_service_dependency_latency_seconds",
    "Service dependency request latency in seconds for reports service",
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
    state_value = 0  # closed
    if state == "open":
        state_value = 1
    elif state == "half-open":
        state_value = 2
    CIRCUIT_BREAKER_STATE.labels(name=name).set(state_value)


def track_circuit_breaker_failure(name: str):
    """Increment circuit breaker failure counter"""
    CIRCUIT_BREAKER_FAILURES.labels(name=name).inc()


def track_circuit_breaker_success(name: str):
    """Increment circuit breaker success counter"""
    CIRCUIT_BREAKER_SUCCESS.labels(name=name).inc()


def track_circuit_breaker_rejection(name: str):
    """Increment circuit breaker rejection counter"""
    CIRCUIT_BREAKER_REJECTED.labels(name=name).inc()


def track_cache_metrics(hit: bool, cache_name: str):
    """Track cache hit/miss metrics"""
    if hit:
        CACHE_HITS.labels(cache=cache_name).inc()
    else:
        CACHE_MISSES.labels(cache=cache_name).inc()


def track_dependency_status(service_name: str, is_available: bool):
    """Track dependency availability status"""
    SERVICE_DEPENDENCY_UP.labels(service=service_name).set(1 if is_available else 0)
