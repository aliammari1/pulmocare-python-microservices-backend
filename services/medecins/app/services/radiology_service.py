import json
import uuid
from datetime import datetime
from typing import Any

import aiohttp

from config import Config
from services.cache_service import CacheService
from services.circuit_breaker import CircuitBreaker
from services.logger_service import logger_service
from services.rabbitmq_client import RabbitMQClient


class RadiologyService:
    """Service for interacting with the radiology (radiologues) service"""

    def __init__(self):
        self.config = Config
        self.rabbitmq_client = RabbitMQClient(self.config)
        self.cache_service = CacheService()
        self.circuit_breaker = CircuitBreaker(
            name="radiology_service",
            failure_threshold=self.config.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout=self.config.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
        )
        self.api_base_url = self._get_service_url()

    def _get_service_url(self) -> str:
        """Get the URL for the radiology service from configuration or service discovery"""
        # In development, use the configured URL
        if self.config.ENV == "development":
            return f"http://{self.config.RADIOLOGUES_SERVICE_HOST}:{self.config.RADIOLOGUES_SERVICE_PORT}"

        # In production, could use service discovery
        # return self._get_service_url_from_consul("radiologues-service")

        # Fallback to default
        return "http://radiologues-service:8084"

    async def get_doctor_radiology_reports(
        self,
        doctor_id: str,
        status: str | None = None,
        page: int = 1,
        limit: int = 10,
    ) -> dict[str, Any]:
        """
        Get radiology reports for a specific doctor
        """
        # Check cache first
        cache_key = f"radiology:reports:doctor:{doctor_id}:{status}:{page}:{limit}"
        cached_data = self.cache_service.get(cache_key)
        if cached_data:
            return json.loads(cached_data)

        # Build query params
        params = {"doctor_id": doctor_id, "page": page, "limit": limit}
        if status:
            params["status"] = status

        # Make request to radiology service
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_base_url}/api/reports"
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        reports = await response.json()
                        # Cache results
                        self.cache_service.set(
                            cache_key,
                            json.dumps(reports),
                            expiry=60,  # Cache for 1 minute
                        )
                        return reports
                    else:
                        error_body = await response.text()
                        logger_service.error(f"Error retrieving radiology reports: {response.status} - {error_body}")
                        return {"items": [], "total": 0, "page": page, "pages": 0}
        except Exception as e:
            logger_service.error(f"Error retrieving radiology reports: {e!s}")
            return {"items": [], "total": 0, "page": page, "pages": 0}

    async def get_radiology_report_details(self, report_id: str) -> dict[str, Any] | None:
        """
        Get details for a specific radiology report
        """
        # Check cache first
        cache_key = f"radiology:report:{report_id}"
        cached_data = self.cache_service.get(cache_key)
        if cached_data:
            return json.loads(cached_data)

        # Make request to radiology service
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_base_url}/api/reports/{report_id}"
                async with session.get(url) as response:
                    if response.status == 200:
                        report = await response.json()
                        # Cache results
                        self.cache_service.set(
                            cache_key,
                            json.dumps(report),
                            expiry=300,  # Cache for 5 minutes
                        )
                        return report
                    else:
                        error_body = await response.text()
                        logger_service.error(f"Error retrieving radiology report: {response.status} - {error_body}")
                        return None
        except Exception as e:
            logger_service.error(f"Error retrieving radiology report: {e!s}")
            return None

    async def request_radiology_examination(
        self,
        doctor_id: str,
        patient_id: str,
        patient_name: str,
        exam_type: str,
        reason: str | None = None,
        urgency: str = "normal",
    ) -> dict[str, Any] | None:
        """
        Request a radiology examination for a patient
        """
        try:
            # Generate a unique request ID
            request_id = f"exam-{uuid.uuid4()}"

            # Send message to RabbitMQ
            success = self.rabbitmq_client.request_radiology_examination(
                request_id=request_id,
                doctor_id=doctor_id,
                patient_id=patient_id,
                patient_name=patient_name,
                exam_type=exam_type,
                reason=reason,
                urgency=urgency,
            )

            if success:
                # Return request information
                return {
                    "request_id": request_id,
                    "doctor_id": doctor_id,
                    "patient_id": patient_id,
                    "patient_name": patient_name,
                    "exam_type": exam_type,
                    "reason": reason,
                    "urgency": urgency,
                    "status": "requested",
                    "created_at": datetime.utcnow().isoformat(),
                }
            else:
                logger_service.error("Failed to request radiology examination via RabbitMQ")
                return None

        except Exception as e:
            logger_service.error(f"Error requesting radiology examination: {e!s}")
            return None

    def close(self):
        """Close any open connections"""
        if self.rabbitmq_client:
            self.rabbitmq_client.close()
