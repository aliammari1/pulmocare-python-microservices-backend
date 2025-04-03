import os

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import \
    OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (BatchSpanProcessor,
                                            ConsoleSpanExporter)
from opentelemetry.trace import NoOpTracer
from services.logger_service import logger_service

from config import Config


class TracingService:
    """Service for OpenTelemetry tracing"""

    def __init__(self, app: FastAPI):
        self.app = app

        self.enabled = True
        self._setup_tracing()

    def _setup_tracing(self):
        """Set up OpenTelemetry tracing"""
        try:
            # Create a resource identifying this service
            service_name = os.getenv("OTEL_SERVICE_NAME", Config.SERVICE_NAME)
            resource = Resource.create(
                {
                    "service.name": service_name,
                    "service.version": Config.VERSION,
                    "deployment.environment": Config.ENV,
                }
            )

            # Create a tracer provider with the resource
            tracer_provider = TracerProvider(resource=resource)
            trace.set_tracer_provider(tracer_provider)

            # Create an OTLP exporter using config
            otlp_endpoint = Config.OTEL_EXPORTER_OTLP_ENDPOINT

            logger_service.info(
                f"Configuring OpenTelemetry with endpoint: {otlp_endpoint}"
            )

            # Use a shorter timeout in development mode to fail faster
            timeout = 3 if Config.ENV == "development" else 10

            try:
                # Create exporter with timeout
                otlp_exporter = OTLPSpanExporter(
                    endpoint=otlp_endpoint, timeout=timeout
                )

                # Add the exporter to the tracer provider using BatchSpanProcessor
                # This will send spans to the collector
                tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

            except Exception as export_error:
                logger_service.warning(
                    f"Failed to configure OTLP exporter: {str(export_error)}"
                )

                # In development mode, use console exporter as fallback
                if Config.ENV == "development":
                    logger_service.info(
                        "Using console exporter as fallback in development mode"
                    )
                    tracer_provider.add_span_processor(
                        BatchSpanProcessor(ConsoleSpanExporter())
                    )

                # Disable tracing completely if specified in config
                if Config.OTEL_DISABLE_ON_ERROR:
                    self.enabled = False
                    logger_service.warning(
                        "Tracing disabled due to connection error (OTEL_DISABLE_ON_ERROR=True)"
                    )

            # Instrument FastAPI and libraries only if tracing is enabled
            if self.enabled:
                # Instrument FastAPI
                FastAPIInstrumentor().instrument_app(self.app)

                # Instrument libraries
                PymongoInstrumentor().instrument()
                RedisInstrumentor().instrument()
                RequestsInstrumentor().instrument()

                # Create a tracer
                self.tracer = trace.get_tracer(__name__)

                logger_service.info("OpenTelemetry tracing initialized successfully")
            else:
                # Create a no-op tracer as fallback
                self.tracer = NoOpTracer()

        except Exception as e:
            logger_service.error(
                f"Failed to initialize OpenTelemetry tracing: {str(e)}"
            )
            # Create a no-op tracer as fallback
            self.tracer = NoOpTracer()
            self.enabled = False

    def is_enabled(self):
        """Check if tracing is enabled"""
        return self.enabled
