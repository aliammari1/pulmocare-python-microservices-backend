import json

import redis
from services.logger_service import logger_service
from services.metrics import track_cache_metrics


class RedisClient:
    """Redis client service for caching"""

    def __init__(self, config):
        self.config = config

        # Initialize Redis client
        self.client = redis.Redis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            password=config.REDIS_PASSWORD,
            decode_responses=True,
        )
        self.ttl = config.CACHE_TTL

    def get(self, key):
        """Get value from cache"""
        try:
            value = self.client.get(key)
            if value:
                track_cache_metrics(hit=True, cache_name="reports")
                return value
            track_cache_metrics(hit=False, cache_name="reports")
            return None
        except Exception as e:
            logger_service.error(f"Redis get error: {str(e)}")
            return None

    def set(self, key, value, ttl=None):
        """Set value in cache"""
        try:
            ttl = ttl or self.ttl
            self.client.setex(key, ttl, value)
            return True
        except Exception as e:
            logger_service.error(f"Redis set error: {str(e)}")
            return False

    def delete(self, key):
        """Delete key from cache"""
        try:
            self.client.delete(key)
            return True
        except Exception as e:
            logger_service.error(f"Redis delete error: {str(e)}")
            return False

    def get_report(self, report_id):
        """Get report from cache"""
        try:
            cached_report = self.get(f"report:{report_id}")
            if cached_report:
                return json.loads(cached_report)
            return None
        except Exception as e:
            logger_service.error(f"Redis get_report error: {str(e)}")
            return None

    def cache_report(self, report_id, report_data):
        """Cache report data"""
        try:
            self.set(f"report:{report_id}", json.dumps(report_data))
            return True
        except Exception as e:
            logger_service.error(f"Redis cache_report error: {str(e)}")
            return False

    def invalidate_report(self, report_id):
        """Invalidate cached report"""
        return self.delete(f"report:{report_id}")

    def close(self):
        """Close Redis connection"""
        try:
            self.client.close()
            logger_service.info("Closed Redis connection")
        except Exception as e:
            logger_service.error(f"Error closing Redis connection: {str(e)}")

    def check_health(self):
        """Check Redis health"""
        try:
            self.client.ping()
            return "UP"
        except Exception as e:
            return f"DOWN: {str(e)}"
