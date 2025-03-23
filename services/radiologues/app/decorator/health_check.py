from flask import jsonify
from pymongo import MongoClient
import redis
import logging
import time
import psutil
import os
from config import Config

logger = logging.getLogger(__name__)

def health_check_middleware(config: Config):
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
                mongo_client = MongoClient(config.get_mongodb_uri(), serverSelectionTimeoutMS=2000)
                mongo_client.admin.command('ping')
                health['checks']['mongodb'] = {'status': 'up'}
            except Exception as e:
                error_msg = str(e)
                health['checks']['mongodb'] = {
                    'status': 'down',
                    'error': error_msg
                }
                health['status'] = 'degraded'

            # Check Redis connection
            try:
                redis_client = redis.from_url(config.REDIS_URL, socket_connect_timeout=2)
                redis_client.ping()
                health['checks']['redis'] = {'status': 'up'}
            except Exception as e:
                error_msg = str(e)
                health['checks']['redis'] = {
                    'status': 'down',
                    'error': error_msg
                }
                health['status'] = 'degraded'

            # System health - using psutil (cross-platform)
            try:
                # Memory info
                memory = psutil.virtual_memory()
                total_mem = memory.total // (1024 * 1024)  # Convert to MB
                used_mem = memory.used // (1024 * 1024)    # Convert to MB
                free_mem = memory.available // (1024 * 1024)  # Convert to MB
                
                # Disk info (C: drive for Windows, / for Linux)
                disk_path = 'C:' if os.name == 'nt' else '/'
                disk = psutil.disk_usage(disk_path)
                total_disk = disk.total // (1024 * 1024 * 1024)  # Convert to GB
                used_disk = disk.used // (1024 * 1024 * 1024)    # Convert to GB
                free_disk = disk.free // (1024 * 1024 * 1024)    # Convert to GB
                
                health['checks']['system'] = {
                    'status': 'up',
                    'memory': {
                        'total': f"{total_mem}M",
                        'used': f"{used_mem}M",
                        'free': f"{free_mem}M"
                    },
                    'disk': {
                        'total': f"{total_disk}G",
                        'used': f"{used_disk}G",
                        'free': f"{free_disk}G"
                    }
                }
            except Exception as e:
                error_msg = str(e)
                health['checks']['system'] = {
                    'status': 'unknown',
                    'error': error_msg
                }
                
            # Determine response code based on overall health
            status_code = 200 if health['status'] == 'healthy' else 503
            return jsonify(health), status_code
        
        app.health_check = health_check
        return app

    return decorator