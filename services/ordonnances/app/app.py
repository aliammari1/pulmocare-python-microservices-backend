import logging

from decorator.health_check import health_check_middleware
from dotenv import load_dotenv
from flask import Flask, jsonify, make_response, request
from flask_cors import CORS
# Add OpenTelemetry imports at the top
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import \
    OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pymongo import MongoClient
from routes.ordonnance_routes import ordonnance_bp
from services.consul_service import ConsulService

from config import Config

load_dotenv()

# Configure OpenTelemetry before creating Flask app
resource = Resource.create(
    {
        "service.name": Config.SERVICE_NAME,
        "service.version": Config.VERSION,
        "deployment.environment": Config.ENV,
    }
)

trace.set_tracer_provider(TracerProvider(resource=resource))
otlp_exporter = OTLPSpanExporter(
    endpoint=Config.OTEL_EXPORTER_OTLP_ENDPOINT + "/v1/traces"
)
span_processor = BatchSpanProcessor(otlp_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)

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

# Initialize MongoDB client for health checks
mongo_client = MongoClient("mongodb://admin:admin@localhost:27017/")

logger = logging.getLogger(__name__)


@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.update(
            {
                "Access-Control-Allow-Origin": request.headers.get("Origin", "*"),
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization, Accept, Origin",
                "Access-Control-Max-Age": "3600",
                "Access-Control-Allow-Credentials": "true",
            }
        )
        return response


@app.after_request
def after_request(response):
    origin = request.headers.get("Origin", "")
    if origin:
        response.headers.add("Access-Control-Allow-Origin", origin)
    response.headers.add(
        "Access-Control-Allow-Headers", "Content-Type,Authorization,Accept,Origin"
    )
    response.headers.add("Access-Control-Allow-Methods", "GET,PUT,POST,DELETE,OPTIONS")
    response.headers.add("Access-Control-Allow-Credentials", "true")
    return response


# Add health check endpoint for Consul
# @app.route('/health', methods=['GET'])
# def health_check():
#     """Health check endpoint for Consul"""
#     try:
#         # Ping MongoDB to verify connection
#         mongo_client.admin.command('ping')

#         return jsonify({
#             'status': 'UP',
#             'service': 'ordonnances-service',
#             'timestamp': datetime.datetime.utcnow().isoformat(),
#             'dependencies': {
#                 'mongodb': 'UP'
#             }
#         }), 200
#     except Exception as e:
#         app.logger.error(f"Health check failed: {str(e)}")
#         return jsonify({
#             'status': 'DOWN',
#             'error': str(e),
#             'timestamp': datetime.datetime.utcnow().isoformat()
#         }), 503

app.register_blueprint(ordonnance_bp, url_prefix="/api/ordonnances")

if __name__ == "__main__":
    # Register with Consul
    try:
        consul_service = ConsulService(Config)
        consul_service.register_service()
        logger.info(f"Registered {Config.SERVICE_NAME} with Consul")
    except Exception as e:
        logger.error(f"Failed to register with Consul: {e}")

    app.run(host=Config.HOST, port=Config.PORT, debug=True)
