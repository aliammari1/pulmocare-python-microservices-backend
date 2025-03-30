import signal
import sys
import time
from datetime import datetime
from functools import wraps

from bson import ObjectId
from decorator.health_check import health_check_middleware
from flask import Blueprint, Flask, jsonify, request, send_file
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Add OpenTelemetry imports at the top
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram, start_http_server
from report_generator import ReportGenerator
from services.logger_service import logger_service
from services.mongodb_client import MongoDBClient
from services.prometheus_service import PrometheusService
from services.rabbitmq_client import RabbitMQClient
from services.redis_client import RedisClient
from services.report_service import ReportService
from services.tracing_service import TracingService
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config

# Initialize metrics
REQUEST_COUNT = Counter(
    "request_count", "Total number of requests", ["method", "endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "request_latency_seconds", "Request latency in seconds", ["method", "endpoint"]
)

# Initialize API blueprint
api = Blueprint("api", __name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Initialize OpenTelemetry instrumentations
FlaskInstrumentor().instrument_app(app)
PymongoInstrumentor().instrument()
RequestsInstrumentor().instrument()
RedisInstrumentor().instrument()

# Apply health check middleware
app = health_check_middleware(Config)(app)

# Initialize services
tracing_service = TracingService(app)
redis_client = RedisClient(Config)
mongodb_client = MongoDBClient(Config)
rabbitmq_client = RabbitMQClient(Config)
prometheus_service = PrometheusService(app, Config)
report_generator = ReportGenerator()
report_service = ReportService(mongodb_client, redis_client, rabbitmq_client)

# Initialize rate limiter with Redis storage
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=Config.RATE_LIMIT_STORAGE_URL,
    storage_options={"password": Config.REDIS_PASSWORD},
    strategy="fixed-window",
)
limiter.init_app(app)


# Handle graceful shutdown
def signal_handler(sig, frame):
    """Handle graceful shutdown"""
    logger_service.info("Received shutdown signal, cleaning up...")
    try:
        rabbitmq_client.close()
        mongodb_client.close()
        redis_client.close()
    except Exception as e:
        logger_service.error(f"Error during cleanup: {str(e)}")

    sys.exit(0)


# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


# Decorators
def handle_service_error(func):
    """Enhanced decorator for service error handling and metrics"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        method = request.method
        endpoint = request.endpoint
        start_time = time.time()

        with tracing_service.tracer.start_as_current_span(
            f"{method} {endpoint}"
        ) as span:
            try:
                response = func(*args, **kwargs)
                status = response[1] if isinstance(response, tuple) else 200
                prometheus_service.record_request(method, endpoint, status)
                return response
            except Exception as e:
                status = 500
                error_response = {
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                    "path": request.path,
                    "method": request.method,
                }
                logger_service.error(f"Service error: {error_response}")
                prometheus_service.record_request(method, endpoint, status)
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))
                return jsonify(error_response), status
            finally:
                prometheus_service.record_latency(
                    method, endpoint, time.time() - start_time
                )

    return wrapper


# API Routes
@api.route("/", methods=["GET"])
@limiter.limit(Config.RATE_LIMIT_DEFAULT)
@handle_service_error
def get_reports():
    """Get all reports with optional filtering"""
    search = request.args.get("search")
    reports = report_service.get_all_reports(search)
    return jsonify(reports)


@api.route("/<report_id>", methods=["GET"])
@limiter.limit(Config.RATE_LIMIT_DEFAULT)
@handle_service_error
def get_report(report_id):
    """Get a specific report by ID"""
    report = report_service.get_report_by_id(report_id)
    if not report:
        return jsonify({"error": "Report not found"}), 404
    return jsonify(report)


@api.route("/", methods=["POST"])
@limiter.limit(Config.RATE_LIMIT_DEFAULT)
@handle_service_error
def create_report():
    """Create a new report"""
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    report = report_service.create_report(data)
    return jsonify(report), 201


@api.route("/<report_id>", methods=["PUT"])
@limiter.limit(Config.RATE_LIMIT_DEFAULT)
@handle_service_error
def update_report(report_id):
    """Update an existing report"""
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    report = report_service.update_report(report_id, data)
    if not report:
        return jsonify({"error": "Report not found"}), 404
    return jsonify(report)


@api.route("/<report_id>", methods=["DELETE"])
@limiter.limit(Config.RATE_LIMIT_DEFAULT)
@handle_service_error
def delete_report(report_id):
    """Delete a report"""
    success = report_service.delete_report(report_id)
    if not success:
        return jsonify({"error": "Report not found"}), 404
    return "", 204


@api.route("/<report_id>/export", methods=["GET"])
@limiter.limit(Config.RATE_LIMIT_DEFAULT)
@handle_service_error
def export_report(report_id):
    """Generate and download PDF report"""
    report = report_service.get_raw_report(report_id)
    if not report:
        return jsonify({"error": "Report not found"}), 404

    # Generate PDF
    output_path = report_generator.generate_pdf(report)

    # Send file
    return send_file(
        output_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"medical_report_{report_id}.pdf",
    )


# Register blueprints
app.register_blueprint(api, url_prefix="/api/reports")

if __name__ == "__main__":
    app.run(host=Config.HOST, port=Config.PORT, debug=True)
