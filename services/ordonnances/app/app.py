import os

from decorator.health_check import health_check_middleware
from dotenv import load_dotenv
from flask import Flask, jsonify, make_response, request
from flask_cors import CORS

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
from pymongo import MongoClient
from routes.ordonnance_routes import ordonnance_bp
from services.logger_service import logger_service
from services.mongodb_client import MongoDBClient
from services.prometheus_service import PrometheusService
from services.rabbitmq_client import RabbitMQClient
from services.redis_client import RedisClient
from services.tracing_service import TracingService

from config import Config

# Determine environment and load corresponding .env file
env = os.getenv("ENV", "development")
dotenv_file = f".env.{env}"
if not os.path.exists(dotenv_file):
    dotenv_file = ".env"
load_dotenv(dotenv_path=dotenv_file)


# Initialize Flask app
app = Flask(__name__)
CORS(app)


# Apply health check middleware
app = health_check_middleware(Config)(app)


# Initialize services
tracing_service = TracingService(app)
redis_client = RedisClient(Config)
mongodb_client = MongoDBClient(Config)
rabbitmq_client = RabbitMQClient(Config)
prometheus_service = PrometheusService(app, Config)


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


app.register_blueprint(ordonnance_bp, url_prefix="/api/ordonnances")

if __name__ == "__main__":
    app.run(host=Config.HOST, port=Config.PORT, debug=True)
