import functools
import logging
import time

from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# RabbitMQ metrics
RABBITMQ_MESSAGES_PUBLISHED = Counter(
    "rabbitmq_messages_published_total",
    "Total number of messages published",
    ["exchange", "routing_key"],
)

RABBITMQ_PUBLISH_LATENCY = Histogram(
    "rabbitmq_publish_latency_seconds",
    "Message publish latency in seconds",
    ["exchange", "routing_key"],
)

RABBITMQ_CONSUME_LATENCY = Histogram(
    "rabbitmq_consume_latency_seconds", "Message consume latency in seconds", ["queue"]
)

RABBITMQ_QUEUE_SIZE = Gauge(
    "rabbitmq_queue_size", "Number of messages in queue", ["queue"]
)

RABBITMQ_CONSUMER_COUNT = Gauge("rabbitmq_consumers", "Number of consumers", ["queue"])

# Circuit breaker metrics
CIRCUIT_BREAKER_STATE = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half-open)",
    ["name"],
)

CIRCUIT_BREAKER_FAILURES = Counter(
    "circuit_breaker_failures_total", "Number of circuit breaker failures", ["name"]
)

CIRCUIT_BREAKER_SUCCESS = Counter(
    "circuit_breaker_success_total", "Number of circuit breaker successes", ["name"]
)

CIRCUIT_BREAKER_REJECTED = Counter(
    "circuit_breaker_rejected_total",
    "Number of requests rejected due to open circuit",
    ["name"],
)

# Cache metrics
CACHE_HITS = Counter("cache_hits_total", "Number of cache hits", ["cache"])

CACHE_MISSES = Counter("cache_misses_total", "Number of cache misses", ["cache"])

CACHE_HIT = Counter(
    "report_cache_hit_total", "Total number of cache hits", ["cache_name"]
)

CACHE_MISS = Counter(
    "report_cache_miss_total", "Total number of cache misses", ["cache_name"]
)

# Service dependency metrics
SERVICE_DEPENDENCY_UP = Gauge(
    "service_dependency_up",
    "Whether a service dependency is available (1=up, 0=down)",
    ["service"],
)

SERVICE_DEPENDENCY_LATENCY = Histogram(
    "service_dependency_latency_seconds",
    "Service dependency request latency in seconds",
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
            logger.exception(f"Error in RabbitMQ operation: {str(e)}")
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
        logger.warning(f"Error updating queue metrics: {str(e)}")


def track_circuit_breaker_state(name: str, state: str):
    """Update circuit breaker state metric"""
    state_values = {"closed": 0, "open": 1, "half_open": 2}
    try:
        CIRCUIT_BREAKER_STATE.labels(name=name).set(state_values.get(state, 0))
        logger.debug(f"Circuit breaker '{name}' state changed to {state}")
    except Exception as e:
        logger.warning(f"Error tracking circuit breaker state: {str(e)}")


def track_circuit_breaker_failure(name: str):
    """Increment circuit breaker failure counter"""
    try:
        CIRCUIT_BREAKER_FAILURES.labels(name=name).inc()
    except Exception as e:
        logger.warning(f"Error tracking circuit breaker failure: {str(e)}")


def track_circuit_breaker_success(name: str):
    """Increment circuit breaker success counter"""
    try:
        CIRCUIT_BREAKER_SUCCESS.labels(name=name).inc()
    except Exception as e:
        logger.warning(f"Error tracking circuit breaker success: {str(e)}")


def track_circuit_breaker_rejection(name: str):
    """Increment circuit breaker rejection counter"""
    try:
        CIRCUIT_BREAKER_REJECTED.labels(name=name).inc()
    except Exception as e:
        logger.warning(f"Error tracking circuit breaker rejection: {str(e)}")


def track_cache_metrics(hit: bool, cache_name: str):
    """Track cache hit/miss metrics"""
    try:
        if hit:
            CACHE_HITS.labels(cache=cache_name).inc()
            CACHE_HIT.labels(cache_name=cache_name).inc()
        else:
            CACHE_MISSES.labels(cache=cache_name).inc()
            CACHE_MISS.labels(cache_name=cache_name).inc()
    except Exception as e:
        logger.warning(f"Error tracking cache metrics: {str(e)}")


def track_dependency_status(service: str, is_available: bool):
    """Track service dependency availability"""
    try:
        SERVICE_DEPENDENCY_UP.labels(service=service).set(1 if is_available else 0)
    except Exception as e:
        logger.warning(f"Error tracking dependency status for {service}: {str(e)}")


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
