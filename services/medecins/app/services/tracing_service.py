import logging
import time
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.trace import NoOpTracer
from config import Config

class TracingService:
    """Service for OpenTelemetry tracing"""
    
    def __init__(self, app):
        self.app = app
        self.logger = logging.getLogger(__name__)
        self.enabled = True
        self._setup_tracing()
    
    def _setup_tracing(self):
        """Set up OpenTelemetry tracing"""
        try:
            # Create a tracer provider
            tracer_provider = TracerProvider()
            trace.set_tracer_provider(tracer_provider)
            
            # Create an OTLP exporter using config
            otlp_endpoint = Config.OTEL_EXPORTER_OTLP_ENDPOINT
            self.logger.info(f"Configuring OpenTelemetry with endpoint: {otlp_endpoint}")
            
            # Use a shorter timeout in development mode to fail faster
            timeout = 3 if Config.ENV == 'development' else 10
            
            try:
                # Create exporter with timeout
                otlp_exporter = OTLPSpanExporter(
                    endpoint=otlp_endpoint,
                    timeout=timeout
                )
                
                # Add the exporter to the tracer provider
                tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
                
            except Exception as export_error:
                self.logger.warning(f"Failed to configure OTLP exporter: {str(export_error)}")
                
                # In development mode, use console exporter as fallback
                if Config.ENV == 'development':
                    self.logger.info("Using console exporter as fallback in development mode")
                    tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
                
                # Disable tracing completely if specified in config
                if Config.OTEL_DISABLE_ON_ERROR:
                    self.enabled = False
                    self.logger.warning("Tracing disabled due to connection error (OTEL_DISABLE_ON_ERROR=True)")
            
            # Instrument Flask and libraries only if tracing is enabled
            if self.enabled:
                # Instrument Flask
                FlaskInstrumentor().instrument_app(self.app)
                
                # Instrument libraries
                PymongoInstrumentor().instrument()
                RedisInstrumentor().instrument()
                
                # Create a tracer
                self.tracer = trace.get_tracer(__name__)
                
                self.logger.info("OpenTelemetry tracing initialized successfully")
            else:
                # Create a no-op tracer as fallback
                self.tracer = NoOpTracer()
                
        except Exception as e:
            self.logger.error(f"Failed to initialize OpenTelemetry tracing: {str(e)}")
            # Create a no-op tracer as fallback
            self.tracer = NoOpTracer()
            self.enabled = False
    
    def is_enabled(self):
        """Check if tracing is enabled"""
        return self.enabled
