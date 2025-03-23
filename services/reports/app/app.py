import os
import sys
import signal
import time
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, Blueprint, send_file
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
import logging
from bson import ObjectId
import json
from config import Config
from services.consul_service import ConsulService
from services.redis_client import RedisClient
from services.mongodb_client import MongoDBClient
from services.rabbitmq_client import RabbitMQClient
from services.prometheus_service import PrometheusService
from services.tracing_service import TracingService
from services.report_service import ReportService
from report_generator import ReportGenerator
from decorator.health_check import health_check_middleware

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Apply health check middleware
app = health_check_middleware(Config)(app)

# Initialize API blueprint
api = Blueprint('api', __name__)

# Set up logging
logging.config.dictConfig(Config.init_logging())
logger = logging.getLogger(__name__)

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
    strategy="fixed-window"
)
limiter.init_app(app)

# Handle graceful shutdown
def signal_handler(sig, frame):
    """Handle graceful shutdown"""
    logger.info("Received shutdown signal, cleaning up...")
    try:
        rabbitmq_client.close()
        mongodb_client.close()
        redis_client.close()
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")
    
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
        
        with tracing_service.tracer.start_as_current_span(f"{method} {endpoint}") as span:
            try:
                response = func(*args, **kwargs)
                status = response[1] if isinstance(response, tuple) else 200
                prometheus_service.record_request(method, endpoint, status)
                return response
            except Exception as e:
                status = 500
                error_response = {
                    'error': str(e),
                    'timestamp': datetime.utcnow().isoformat(),
                    'path': request.path,
                    'method': request.method
                }
                logger.error(f"Service error: {error_response}")
                prometheus_service.record_request(method, endpoint, status)
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))
                return jsonify(error_response), status
            finally:
                prometheus_service.record_latency(method, endpoint, time.time() - start_time)
    return wrapper

# API Routes
@api.route('/', methods=['GET'])
@limiter.limit(Config.RATE_LIMIT_DEFAULT)
@handle_service_error
def get_reports():
    """Get all reports with optional filtering"""
    search = request.args.get('search')
    reports = report_service.get_all_reports(search)
    return jsonify(reports)

@api.route('/<report_id>', methods=['GET'])
@limiter.limit(Config.RATE_LIMIT_DEFAULT)
@handle_service_error
def get_report(report_id):
    """Get a specific report by ID"""
    report = report_service.get_report_by_id(report_id)
    if not report:
        return jsonify({'error': 'Report not found'}), 404
    return jsonify(report)

@api.route('/', methods=['POST'])
@limiter.limit(Config.RATE_LIMIT_DEFAULT)
@handle_service_error
def create_report():
    """Create a new report"""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    report = report_service.create_report(data)
    return jsonify(report), 201

@api.route('/<report_id>', methods=['PUT'])
@limiter.limit(Config.RATE_LIMIT_DEFAULT)
@handle_service_error
def update_report(report_id):
    """Update an existing report"""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    report = report_service.update_report(report_id, data)
    if not report:
        return jsonify({'error': 'Report not found'}), 404
    return jsonify(report)

@api.route('/<report_id>', methods=['DELETE'])
@limiter.limit(Config.RATE_LIMIT_DEFAULT)
@handle_service_error
def delete_report(report_id):
    """Delete a report"""
    success = report_service.delete_report(report_id)
    if not success:
        return jsonify({'error': 'Report not found'}), 404
    return '', 204

@api.route('/<report_id>/export', methods=['GET'])
@limiter.limit(Config.RATE_LIMIT_DEFAULT)
@handle_service_error
def export_report(report_id):
    """Generate and download PDF report"""
    report = report_service.get_raw_report(report_id)
    if not report:
        return jsonify({'error': 'Report not found'}), 404
    
    # Generate PDF
    output_path = report_generator.generate_pdf(report)
    
    # Send file
    return send_file(
        output_path,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"medical_report_{report_id}.pdf"
    )

# Start the application
if __name__ == '__main__':
    # Start Prometheus metrics server
    prometheus_service.start_metrics_server()
    
    # Register with Consul
    ConsulService(Config).register_service()
    
    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=True
    )

