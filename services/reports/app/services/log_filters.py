import logging
from opentelemetry import trace


class OpenTelemetryTraceContextFilter(logging.Filter):
    """Filter that adds OpenTelemetry trace and span IDs to log records"""

    def filter(self, record):
        span_context = trace.get_current_span().get_span_context()
        if span_context and span_context.is_valid:
            record.otelTraceID = format(span_context.trace_id, "032x")
            record.otelSpanID = format(span_context.span_id, "016x")
        else:
            record.otelTraceID = "00" * 16
            record.otelSpanID = "00" * 8
        return True
