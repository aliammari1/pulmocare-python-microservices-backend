import json
from datetime import datetime
from typing import Any, Dict, Optional

import aiohttp
from services.cache_service import CacheService
from services.circuit_breaker import CircuitBreaker
from services.logger_service import logger_service
from services.rabbitmq_client import RabbitMQClient

from config import Config


class PrescriptionService:
    """Service for interacting with the prescription (ordonnances) service"""

    def __init__(self):
        self.config = Config
        self.rabbitmq_client = RabbitMQClient(self.config)
        self.cache_service = CacheService()
        self.circuit_breaker = CircuitBreaker(
            name="prescription_service",
            failure_threshold=self.config.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout=self.config.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
        )
        self.api_base_url = self._get_service_url()

    def _get_service_url(self) -> str:
        """Get the URL for the prescription service from configuration or service discovery"""
        # In development, use the configured URL
        if self.config.ENV == "development":
            return f"http://{self.config.ORDONNANCES_SERVICE_HOST}:{self.config.ORDONNANCES_SERVICE_PORT}"

        # In production, could use service discovery
        # return self._get_service_url_from_consul("ordonnances-service")

        # Fallback to default
        return "http://ordonnances-service:8083"

    async def get_doctor_prescriptions(
        self,
        doctor_id: str,
        status: Optional[str] = None,
        page: int = 1,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Get prescriptions for a specific doctor
        """
        try:
            # Define cache key
            cache_key = f"doctor_prescriptions:{doctor_id}:{status}:{page}:{limit}"

            # Check cache first
            cached_data = self.cache_service.get(cache_key)
            if cached_data:
                logger_service.debug(f"Using cached prescriptions for {doctor_id}")
                return json.loads(cached_data)

            # Use circuit breaker pattern for API calls
            if not self.circuit_breaker.is_closed():
                logger_service.warning(
                    "Circuit breaker open, returning empty prescriptions list"
                )
                return {"items": [], "total": 0, "page": page, "pages": 0}

            # Prepare query parameters
            params = {
                "doctor_id": doctor_id,
                "limit": limit,
                "skip": (page - 1) * limit,
            }

            if status:
                params["status"] = status

            # Call the prescriptions service API
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_base_url}/api/ordonnances"

                logger_service.debug(
                    f"Fetching prescriptions from {url} with params {params}"
                )

                async with session.get(
                    url, params=params, timeout=self.config.REQUEST_TIMEOUT
                ) as response:
                    if response.status == 200:
                        # Record successful call
                        self.circuit_breaker.record_success()

                        # Parse and cache response
                        prescriptions = await response.json()
                        self.cache_service.set(
                            cache_key,
                            json.dumps(prescriptions),
                            ttl=self.config.CACHE_TTL,
                        )

                        return prescriptions
                    else:
                        # Record failure
                        self.circuit_breaker.record_failure()

                        # Log the error
                        error_text = await response.text()
                        logger_service.error(
                            f"Error getting prescriptions: HTTP {response.status}, {error_text}"
                        )

                        # Return empty result as fallback
                        return {"items": [], "total": 0, "page": page, "pages": 0}

        except aiohttp.ClientError as e:
            # Record failure
            self.circuit_breaker.record_failure()

            logger_service.error(f"HTTP error when getting prescriptions: {str(e)}")
            return {"items": [], "total": 0, "page": page, "pages": 0}

        except Exception as e:
            logger_service.error(
                f"Unexpected error when getting prescriptions: {str(e)}"
            )
            return {"items": [], "total": 0, "page": page, "pages": 0}

    async def get_prescription_details(
        self, prescription_id: str, doctor_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get details for a specific prescription
        """
        try:
            # Define cache key
            cache_key = f"prescription:{prescription_id}"

            # Check cache first
            cached_data = self.cache_service.get(cache_key)
            if cached_data:
                logger_service.debug(
                    f"Using cached prescription data for {prescription_id}"
                )
                return json.loads(cached_data)

            # Use circuit breaker pattern for API calls
            if not self.circuit_breaker.is_closed():
                logger_service.warning(
                    "Circuit breaker open, returning None for prescription details"
                )
                return None

            # Call the prescriptions service API
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_base_url}/api/ordonnances/{prescription_id}"

                logger_service.debug(f"Fetching prescription details from {url}")

                async with session.get(
                    url, timeout=self.config.REQUEST_TIMEOUT
                ) as response:
                    if response.status == 200:
                        # Record successful call
                        self.circuit_breaker.record_success()

                        # Parse and cache response
                        prescription = await response.json()

                        # Verify that the prescription belongs to the doctor
                        if prescription.get("doctor_id") != doctor_id:
                            logger_service.warning(
                                f"Doctor {doctor_id} attempted to access prescription {prescription_id} "
                                f"belonging to doctor {prescription.get('doctor_id')}"
                            )
                            return None

                        self.cache_service.set(
                            cache_key,
                            json.dumps(prescription),
                            ttl=self.config.CACHE_TTL,
                        )

                        return prescription
                    elif response.status == 404:
                        return None
                    else:
                        # Record failure
                        self.circuit_breaker.record_failure()

                        # Log the error
                        error_text = await response.text()
                        logger_service.error(
                            f"Error getting prescription details: HTTP {response.status}, {error_text}"
                        )

                        return None

        except aiohttp.ClientError as e:
            # Record failure
            self.circuit_breaker.record_failure()

            logger_service.error(
                f"HTTP error when getting prescription details: {str(e)}"
            )
            return None

        except Exception as e:
            logger_service.error(
                f"Unexpected error when getting prescription details: {str(e)}"
            )
            return None

    async def renew_prescription(
        self, prescription_id: str, doctor_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Renew an existing prescription
        """
        try:
            # Get the original prescription first to verify ownership
            original_prescription = await self.get_prescription_details(
                prescription_id=prescription_id, doctor_id=doctor_id
            )

            if not original_prescription:
                logger_service.warning(
                    f"Prescription {prescription_id} not found or not accessible"
                )
                return None

            # Use circuit breaker pattern for API calls
            if not self.circuit_breaker.is_closed():
                logger_service.warning(
                    "Circuit breaker open, cannot renew prescription"
                )
                return None

            # Send a message to the prescription service
            message = {
                "prescription_id": prescription_id,
                "doctor_id": doctor_id,
                "action": "renewed",
                "timestamp": datetime.utcnow().isoformat(),
            }

            # Publish message
            self.rabbitmq_client.publish_message(
                exchange="medical.events",
                routing_key="doctor.prescription.renewed",
                message=message,
            )

            logger_service.info(
                f"Sent renewal request for prescription {prescription_id}"
            )

            # This will be async in reality - the actual renewed prescription
            # will be processed by the prescription service and sent back via another event,
            # but for now, we'll create a mock renewal response
            renewal_id = (
                f"renewed-{prescription_id}-{int(datetime.utcnow().timestamp())}"
            )

            renewed_prescription = {
                **original_prescription,
                "id": renewal_id,
                "original_prescription_id": prescription_id,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "status": "created",
                "renewal_count": original_prescription.get("renewal_count", 0) + 1,
            }

            # Cache the new prescription
            cache_key = f"prescription:{renewal_id}"
            self.cache_service.set(
                cache_key, json.dumps(renewed_prescription), ttl=self.config.CACHE_TTL
            )

            # Invalidate the doctor prescriptions cache
            self.cache_service.delete_pattern(f"doctor_prescriptions:{doctor_id}:*")

            return renewed_prescription

        except Exception as e:
            logger_service.error(f"Error renewing prescription: {str(e)}")
            return None

    async def cancel_prescription(
        self, prescription_id: str, doctor_id: str, reason: Optional[str] = None
    ) -> bool:
        """
        Cancel an existing prescription
        """
        try:
            # Get the original prescription first to verify ownership
            original_prescription = await self.get_prescription_details(
                prescription_id=prescription_id, doctor_id=doctor_id
            )

            if not original_prescription:
                logger_service.warning(
                    f"Prescription {prescription_id} not found or not accessible"
                )
                return False

            # Use circuit breaker pattern for API calls
            if not self.circuit_breaker.is_closed():
                logger_service.warning(
                    "Circuit breaker open, cannot cancel prescription"
                )
                return False

            # Send a message to the prescription service
            message = {
                "prescription_id": prescription_id,
                "doctor_id": doctor_id,
                "action": "cancelled",
                "reason": reason,
                "patient_id": original_prescription.get("patient_id"),
                "timestamp": datetime.utcnow().isoformat(),
            }

            # Publish message
            self.rabbitmq_client.publish_message(
                exchange="medical.events",
                routing_key="doctor.prescription.cancelled",
                message=message,
            )

            logger_service.info(
                f"Sent cancellation request for prescription {prescription_id}"
            )

            # Invalidate caches
            self.cache_service.delete(f"prescription:{prescription_id}")
            self.cache_service.delete_pattern(f"doctor_prescriptions:{doctor_id}:*")

            return True

        except Exception as e:
            logger_service.error(f"Error cancelling prescription: {str(e)}")
            return False
