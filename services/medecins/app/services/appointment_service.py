from typing import Dict, Optional

import httpx
from services.logger_service import logger_service


class AppointmentService:
    """Service to manage appointments between doctors and patients"""

    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.timeout = httpx.Timeout(30.0)
        self.client = httpx.AsyncClient(timeout=self.timeout)

    async def get_doctor_appointments(
        self,
        doctor_id: str,
        status: Optional[str] = None,
        page: int = 1,
        limit: int = 10,
    ) -> Dict:
        """
        Get appointments for a specific doctor
        """
        try:
            url = f"{self.base_url}/api/appointments/doctor/{doctor_id}"

            params = {"page": page, "limit": limit}
            if status:
                params["status"] = status

            response = await self.client.get(url, params=params)

            if response.status_code == 200:
                return response.json()
            else:
                logger_service.error(
                    f"Error getting doctor appointments: {response.status_code} - {response.text}"
                )
                return {"items": [], "total": 0, "page": page, "limit": limit}

        except Exception as e:
            logger_service.error(f"Error in get_doctor_appointments: {str(e)}")
            return {"items": [], "total": 0, "page": page, "limit": limit}

    async def get_appointment_details(
        self, appointment_id: str, doctor_id: str
    ) -> Optional[Dict]:
        """
        Get details for a specific appointment
        """
        try:
            url = f"{self.base_url}/api/appointments/{appointment_id}"

            response = await self.client.get(url)

            if response.status_code == 200:
                appointment = response.json()

                # Verify that this appointment belongs to the specified doctor
                if appointment.get("doctor_id") != doctor_id:
                    logger_service.warning(
                        f"Doctor {doctor_id} attempted to access appointment {appointment_id} "
                        f"belonging to another doctor"
                    )
                    return None

                return appointment
            elif response.status_code == 404:
                return None
            else:
                logger_service.error(
                    f"Error getting appointment details: {response.status_code} - {response.text}"
                )
                return None

        except Exception as e:
            logger_service.error(f"Error in get_appointment_details: {str(e)}")
            return None

    async def update_appointment_status(
        self,
        appointment_id: str,
        doctor_id: str,
        new_status: str,
        reason: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Update the status of an appointment (accept/reject)
        """
        try:
            # First verify the appointment exists and belongs to this doctor
            appointment = await self.get_appointment_details(appointment_id, doctor_id)

            if not appointment:
                return None

            url = f"{self.base_url}/api/appointments/{appointment_id}/status"

            data = {
                "status": new_status,
            }

            if reason:
                data["reason"] = reason

            response = await self.client.put(url, json=data)

            if response.status_code == 200:
                return response.json()
            else:
                logger_service.error(
                    f"Error updating appointment status: {response.status_code} - {response.text}"
                )
                return None

        except Exception as e:
            logger_service.error(f"Error in update_appointment_status: {str(e)}")
            return None

    async def accept_appointment(
        self, appointment_id: str, doctor_id: str
    ) -> Optional[Dict]:
        """
        Accept an appointment
        """
        return await self.update_appointment_status(
            appointment_id=appointment_id, doctor_id=doctor_id, new_status="accepted"
        )

    async def reject_appointment(
        self, appointment_id: str, doctor_id: str, reason: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Reject an appointment
        """
        return await self.update_appointment_status(
            appointment_id=appointment_id,
            doctor_id=doctor_id,
            new_status="rejected",
            reason=reason,
        )

    def close(self):
        """
        Close the HTTP client session
        """
        import asyncio

        try:
            asyncio.create_task(self.client.aclose())
        except Exception as e:
            logger_service.error(f"Error closing HTTP client: {str(e)}")
