from fastapi import APIRouter

from services.logger_service import logger_service

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint for the appointments service"""
    logger_service.info("Health check requested")
    return {"status": "healthy", "service": "appointments"}


@router.get("/readiness")
async def readiness_check():
    """Readiness check endpoint for the appointments service"""
    logger_service.info("Readiness check requested")
    return {"status": "ready", "service": "appointments"}
