import socket

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

from config import Config


class MetricsService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MetricsService, cls).__new__(cls)
            cls._instance._setup_metrics()
        return cls._instance

    def _setup_metrics(self):
        """Set up OpenTelemetry metrics"""
        try:
            # Create a Resource to identify the service
            resource = Resource.create(
                {
                    "service.name": Config.SERVICE_NAME,
                    "service.instance.id": socket.gethostname(),
                }
            )

            # Create the metric exporter
            exporter = OTLPMetricExporter(
                endpoint=f"http://{'localhost' if Config.ENV == 'development' else 'otel-collector'}:4317",
                insecure=True,
            )

            # Create the metric reader
            reader = PeriodicExportingMetricReader(exporter)

            # Create the meter provider
            meter_provider = MeterProvider(resource=resource, metric_readers=[reader])

            # Set the global meter provider
            metrics.set_meter_provider(meter_provider)

            # Create a meter
            self.meter = metrics.get_meter(Config.SERVICE_NAME)

            # Create some basic counters and gauges
            self.request_counter = self.meter.create_counter(name="request_counter", description="Counts the number of requests")
            self.error_counter = self.meter.create_counter(name="error_counter", description="Counts the number of errors")
            self.response_time = self.meter.create_histogram(name="response_time", description="Tracks response time distribution")

        except Exception as e:
            print(f"Failed to initialize OpenTelemetry metrics: {e!s}")

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = MetricsService()
        return cls._instance

    def increment_requests(self, attributes=None):
        self.request_counter.add(1, attributes=attributes)

    def increment_errors(self, attributes=None):
        self.error_counter.add(1, attributes=attributes)

    def record_response_time(self, duration, attributes=None):
        self.response_time.record(duration, attributes=attributes)


# Singleton instance
metrics_service = MetricsService.get_instance()
