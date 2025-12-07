import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from config import Config


def health_check_middleware(config: Config):
    """Middleware to add health check endpoint to FastAPI apps"""

    def decorator(app: FastAPI):
        @app.get("/health")
        def health_check():
            health = {
                "status": "healthy",
                "service": config.SERVICE_NAME,
                "version": config.VERSION,
                "timestamp": int(time.time()),
            }
            return JSONResponse(content=health, status_code=200)

        app.health_check = health_check
        return app

    return decorator
