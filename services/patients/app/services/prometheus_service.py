from prometheus_client import Counter, Histogram, start_http_server
from prometheus_flask_exporter import PrometheusMetrics
from services.logger_service import logger_service


class PrometheusService:
    """Service for Prometheus metrics"""

    def __init__(self, app, config):
        self.app = app
        self.config = config

        # Initialize Prometheus metrics
        self.metrics = PrometheusMetrics(app)
        self.metrics.info(
            "patients_service_info", "Patients service info", version="1.0.0"
        )

        # Define custom metrics
        self.request_count = Counter(
            "patients_service_requests_total",
            "Total requests to patients service",
            ["method", "endpoint", "status"],
        )
        self.request_latency = Histogram(
            "patients_service_request_latency_seconds",
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
            logger_service.info(
                f"Prometheus metrics server started on port {self.config.METRICS_PORT}"
            )
        except OSError as e:
            if e.errno == 98:  # Address already in use
                fallback_port = self.config.METRICS_PORT + 1
                logger_service.warning(
                    f"Port {self.config.METRICS_PORT} is already in use. Trying fallback port {fallback_port}"
                )
                try:
                    start_http_server(fallback_port)
                    logger_service.info(
                        f"Prometheus metrics server started on fallback port {fallback_port}"
                    )
                except Exception as fallback_error:
                    logger_service.error(
                        f"Failed to start Prometheus metrics server on fallback port: {str(fallback_error)}"
                    )
            else:
                logger_service.error(
                    f"Failed to start Prometheus metrics server: {str(e)}"
                )
