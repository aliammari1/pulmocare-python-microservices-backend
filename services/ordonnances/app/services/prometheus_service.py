import logging

from prometheus_client import Counter, Histogram, start_http_server
from prometheus_flask_exporter import PrometheusMetrics


class PrometheusService:
    """Service for Prometheus metrics"""

    def __init__(self, app, config):
        self.app = app
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Initialize Prometheus metrics
        self.metrics = PrometheusMetrics(app)
        self.metrics.info(
            "ordonnances_service_info", "Ordonnances service info", version="1.0.0"
        )

        # Define custom metrics
        self.request_count = Counter(
            "ordonnances_service_requests_total",
            "Total requests to ordonnances service",
            ["method", "endpoint", "status"],
        )
        self.request_latency = Histogram(
            "ordonnances_service_request_latency_seconds",
            "Request latency in seconds",
            ["method", "endpoint"],
        )

    def record_request(self, method, endpoint, status):
        """Record request metrics"""
        self.request_count.labels(method=method, endpoint=endpoint, status=status).inc()

    def record_latency(self, method, endpoint, duration):
        """Record request latency"""
        self.request_latency.labels(method=method, endpoint=endpoint).observe(duration)

    def start_metrics_server(self):
        """Start Prometheus metrics server"""
        try:
            start_http_server(self.config.METRICS_PORT)
            self.logger.info(
                f"Prometheus metrics server started on port {self.config.METRICS_PORT}"
            )
        except OSError as e:
            if e.errno == 98:  # Address already in use
                fallback_port = self.config.METRICS_PORT + 1
                self.logger.warning(
                    f"Port {self.config.METRICS_PORT} is already in use. Trying fallback port {fallback_port}"
                )
                try:
                    start_http_server(fallback_port)
                    self.logger.info(
                        f"Prometheus metrics server started on fallback port {fallback_port}"
                    )
                except Exception as fallback_error:
                    self.logger.error(
                        f"Failed to start Prometheus metrics server on fallback port: {str(fallback_error)}"
                    )
            else:
                self.logger.error(
                    f"Failed to start Prometheus metrics server: {str(e)}"
                )
