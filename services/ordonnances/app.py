from flask import Flask, request, make_response, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from routes.ordonnance_routes import ordonnance_bp
from config import Config
from services.consul_service import ConsulService
import logging
from decorator.health_check import health_check_middleware
from pymongo import MongoClient

load_dotenv()

app = Flask(__name__)
CORS(app)

# Apply health check middleware
app = health_check_middleware(Config)(app)

# Initialize MongoDB client for health checks
mongo_client = MongoClient('mongodb://admin:admin@localhost:27017/')

logger = logging.getLogger(__name__)



@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.update({
            "Access-Control-Allow-Origin": request.headers.get("Origin", "*"),
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, Accept, Origin",
            "Access-Control-Max-Age": "3600",
            "Access-Control-Allow-Credentials": "true"
        })
        return response

@app.after_request
def after_request(response):
    origin = request.headers.get('Origin', '')
    if origin:
        response.headers.add('Access-Control-Allow-Origin', origin)
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,Accept,Origin')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
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

app.register_blueprint(ordonnance_bp, url_prefix='/api/ordonnances')

if __name__ == '__main__':
    # Register with Consul
    try:
        consul_service = ConsulService(Config)
        consul_service.register_service()
        logger.info(f"Registered {Config.SERVICE_NAME} with Consul")
    except Exception as e:
        logger.error(f"Failed to register with Consul: {e}")
        
    app.run(host=Config.HOST, port=Config.PORT, debug=True)
