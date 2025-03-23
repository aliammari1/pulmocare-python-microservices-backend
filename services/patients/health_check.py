from flask import jsonify
from functools import wraps
from pymongo import MongoClient
import redis
import logging
import os
import time

logger = logging.getLogger(__name__)

def health_check_middleware(config):
    """Middleware to add health check endpoint to Flask apps"""
    def decorator(app):
        @app.route('/health', methods=['GET'])
        def health_check():
            health = {
                'status': 'healthy',
                'service': config.SERVICE_NAME,
                'version': config.VERSION,
                'timestamp': int(time.time()),
                'checks': {}
            }

            # Check MongoDB connection
            try:
                mongo_client = MongoClient(config.get_mongodb_uri())
                mongo_client.admin.command('ping')
                health['checks']['mongodb'] = {'status': 'up'}
            except Exception as e:
                health['checks']['mongodb'] = {
                    'status': 'down',
                    'error': str(e)
                }
                health['status'] = 'degraded'

            # Check Redis connection
            try:
                redis_client = redis.from_url(config.REDIS_URL)
                redis_client.ping()
                health['checks']['redis'] = {'status': 'up'}
            except Exception as e:
                health['checks']['redis'] = {
                    'status': 'down',
                    'error': str(e)
                }
                health['status'] = 'degraded'

            # System health
            try:
                memory = os.popen('free -m').readlines()[1].split()
                disk = os.popen('df -h /').readlines()[1].split()
                health['checks']['system'] = {
                    'status': 'up',
                    'memory': {
                        'total': memory[1],
                        'used': memory[2],
                        'free': memory[3]
                    },
                    'disk': {
                        'total': disk[1],
                        'used': disk[2],
                        'free': disk[3]
                    }
                }
            except Exception as e:
                health['checks']['system'] = {
                    'status': 'unknown',
                    'error': str(e)
                }

            # Determine response code based on overall health
            status_code = 200 if health['status'] == 'healthy' else 503
            return jsonify(health), status_code

        return app

    return decorator