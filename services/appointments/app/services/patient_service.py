import httpx
from services.circuit_breaker import CircuitBreaker
from services.logger_service import logger_service


class PatientService:
    """Service for interacting with the Patients API"""

    def __init__(self, config):
        self.config = config
        self.base_url = (
            f"http://{config.PATIENTS_SERVICE_HOST}:{config.PATIENTS_SERVICE_PORT}/api"
        )
        self.timeout = config.REQUEST_TIMEOUT
        # Initialize circuit breaker
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=config.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout=config.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
            name="patients-service",
        )

    async def get_patient_by_id(self, patient_id, auth_header=None):
        """Get patient details by ID"""
        try:
            # Use circuit breaker to handle failures
            return await self.circuit_breaker.call(
                self._get_patient_by_id, patient_id, auth_header
            )
        except Exception as e:
            logger_service.error(
                f"Error fetching patient with ID {patient_id}: {str(e)}"
            )
            return None

    async def _get_patient_by_id(self, patient_id, auth_header=None):
        """Internal method to get patient details from patients service"""
        headers = {}
        if auth_header:
            headers["Authorization"] = auth_header

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/patients/{patient_id}", headers=headers
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger_service.error(
                    f"Error fetching patient: HTTP {response.status_code} - {response.text}"
                )
                return None

    async def verify_patient_exists(self, patient_id, auth_header=None):
        """Verify if a patient exists"""
        try:
            patient = await self.get_patient_by_id(patient_id, auth_header)
            return patient is not None
        except Exception as e:
            logger_service.error(f"Error verifying patient existence: {str(e)}")
            return False

    async def get_patient_medical_history(self, patient_id, auth_header=None):
        """Get patient medical history"""
        try:
            return await self.circuit_breaker.call(
                self._get_patient_medical_history, patient_id, auth_header
            )
        except Exception as e:
            logger_service.error(f"Error fetching patient medical history: {str(e)}")
            return {}

    async def _get_patient_medical_history(self, patient_id, auth_header=None):
        """Internal method to get patient medical history from patients service"""
        headers = {}
        if auth_header:
            headers["Authorization"] = auth_header

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/patients/{patient_id}/medical-history",
                headers=headers,
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger_service.error(
                    f"Error fetching patient medical history: HTTP {response.status_code} - {response.text}"
                )
                return {}

    async def notify_patient_appointment(
            self, patient_id, appointment_data, auth_header=None
    ):
        """Notify patient of a new appointment"""
        try:
            return await self.circuit_breaker.call(
                self._notify_patient_appointment,
                patient_id,
                appointment_data,
                auth_header,
            )
        except Exception as e:
            logger_service.error(f"Error notifying patient of appointment: {str(e)}")
            return False

    async def _notify_patient_appointment(
            self, patient_id, appointment_data, auth_header=None
    ):
        """Internal method to notify patient of a new appointment"""
        headers = {"Content-Type": "application/json"}
        if auth_header:
            headers["Authorization"] = auth_header

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/patients/{patient_id}/appointments/notify",
                json=appointment_data,
                headers=headers,
            )

            if response.status_code in (200, 201, 204):
                return True
            else:
                logger_service.error(
                    f"Error notifying patient of appointment: HTTP {response.status_code} - {response.text}"
                )
                return False
