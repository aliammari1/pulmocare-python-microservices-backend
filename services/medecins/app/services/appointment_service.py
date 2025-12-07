from typing import Dict, Optional

import httpx
from services.logger_service import logger_service


class AppointmentService:
    """Service to manage appointments between doctors and patients"""

    def __init__(self):
        # Update to use the proper service name in Docker network instead of localhost
        self.base_url = "http://medecins-service:8081"
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
            url = f"{self.base_url}/api/integration/appointments/doctor/{doctor_id}"

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
                return {
                    "items": [],
                    "total": 0,
                    "page": page,
                    "limit": limit,
                    "pages": 0,
                }

        except Exception as e:
            logger_service.error(f"Error in get_doctor_appointments: {str(e)}")
            return {"items": [], "total": 0, "page": page, "limit": limit, "pages": 0}

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

    async def reschedule_appointment(
            self,
            appointment_id: str,
            doctor_id: str,
            new_time: str,
            reason: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Reschedule an appointment to a new time
        """
        try:
            # First verify the appointment exists and belongs to this doctor
            appointment = await self.get_appointment_details(appointment_id, doctor_id)

            if not appointment:
                return None

            url = f"{self.base_url}/api/appointments/{appointment_id}/reschedule"

            data = {
                "new_time": new_time,
            }

            if reason:
                data["reason"] = reason

            response = await self.client.put(url, json=data)

            if response.status_code == 200:
                return response.json()
            else:
                logger_service.error(
                    f"Error rescheduling appointment: {response.status_code} - {response.text}"
                )
                return None

        except Exception as e:
            logger_service.error(f"Error in reschedule_appointment: {str(e)}")
            return None

    async def add_appointment_notes(
            self,
            appointment_id: str,
            doctor_id: str,
            notes: str,
    ) -> Optional[Dict]:
        """
        Add notes to an existing appointment
        """
        try:
            # First verify the appointment exists and belongs to this doctor
            appointment = await self.get_appointment_details(appointment_id, doctor_id)

            if not appointment:
                return None

            url = f"{self.base_url}/api/appointments/{appointment_id}/notes"

            data = {
                "notes": notes,
            }

            response = await self.client.put(url, json=data)

            if response.status_code == 200:
                return response.json()
            else:
                logger_service.error(
                    f"Error adding appointment notes: {response.status_code} - {response.text}"
                )
                return None

        except Exception as e:
            logger_service.error(f"Error in add_appointment_notes: {str(e)}")
            return None

    async def get_patient_appointments(
            self,
            doctor_id: str,
            patient_id: str,
            status: Optional[str] = None,
            page: int = 1,
            limit: int = 10,
    ) -> Dict:
        """
        Get appointments between a specific doctor and patient
        """
        try:
            url = f"{self.base_url}/api/appointments/doctor/{doctor_id}/patient/{patient_id}"

            params = {"page": page, "limit": limit}
            if status:
                params["status"] = status

            response = await self.client.get(url, params=params)

            if response.status_code == 200:
                return response.json()
            else:
                logger_service.error(
                    f"Error getting patient appointments: {response.status_code} - {response.text}"
                )
                return {
                    "items": [],
                    "total": 0,
                    "page": page,
                    "limit": limit,
                    "pages": 0,
                }

        except Exception as e:
            logger_service.error(f"Error in get_patient_appointments: {str(e)}")
            return {"items": [], "total": 0, "page": page, "limit": limit, "pages": 0}

    async def create_appointment(
            self,
            doctor_id: str,
            patient_id: str,
            patient_name: str,
            requested_time: str,
            reason: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Create a new appointment for a patient with this doctor
        """
        try:
            url = f"{self.base_url}/api/appointments"

            data = {
                "doctor_id": doctor_id,
                "patient_id": patient_id,
                "patient_name": patient_name,
                "requested_time": requested_time,
            }

            if reason:
                data["reason"] = reason

            response = await self.client.post(url, json=data)

            if response.status_code == 201:
                return response.json()
            else:
                logger_service.error(
                    f"Error creating appointment: {response.status_code} - {response.text}"
                )
                return None

        except Exception as e:
            logger_service.error(f"Error in create_appointment: {str(e)}")
            return None

    async def cancel_appointment(
            self,
            appointment_id: str,
            doctor_id: str,
            reason: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Cancel an existing appointment
        """
        return await self.update_appointment_status(
            appointment_id=appointment_id,
            doctor_id=doctor_id,
            new_status="cancelled",
            reason=reason,
        )

    async def complete_appointment(
            self,
            appointment_id: str,
            doctor_id: str,
            notes: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Mark an appointment as completed
        """
        try:
            # First verify the appointment exists and belongs to this doctor
            appointment = await self.get_appointment_details(appointment_id, doctor_id)

            if not appointment:
                return None

            url = f"{self.base_url}/api/appointments/{appointment_id}/complete"

            data = {}
            if notes:
                data["notes"] = notes

            response = await self.client.put(url, json=data)

            if response.status_code == 200:
                return response.json()
            else:
                logger_service.error(
                    f"Error completing appointment: {response.status_code} - {response.text}"
                )
                return None

        except Exception as e:
            logger_service.error(f"Error in complete_appointment: {str(e)}")
            return None

    def close(self):
        """
        Close the HTTP client session
        """
        import asyncio

        try:
            asyncio.create_task(self.client.aclose())
        except Exception as e:
            logger_service.error(f"Error closing HTTP client: {str(e)}")
