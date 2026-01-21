from datetime import datetime, timedelta
from typing import Any

import httpx
from pymongo import ReturnDocument

from config import Config
from models.appointment import (
    Appointment,
    AppointmentCreate,
    AppointmentNotification,
    AppointmentStatus,
    AppointmentUpdate,
    ProviderSchedule,
    ProviderType,
    TimeSlot,
)
from services.logger_service import logger_service
from services.medecin_service import MedecinService
from services.mongodb_client import MongoDBClient
from services.patient_service import PatientService
from services.rabbitmq_client import RabbitMQClient


class AppointmentService:
    """Service to manage medical appointments"""

    def __init__(self, config=None):
        if config is None:
            config = Config()

        self.config = config
        self.timeout = httpx.Timeout(config.REQUEST_TIMEOUT)
        self.client = httpx.AsyncClient(timeout=self.timeout)

        # Initialize services
        self.mongodb_client = MongoDBClient(config)
        self.rabbitmq_client = RabbitMQClient(config)
        self.medecin_service = MedecinService(config)
        self.patient_service = PatientService(config)

        # MongoDB collections
        self.db = self.mongodb_client.db
        self.appointments_collection = self.mongodb_client.appointments_collection

    async def create_appointment(self, appointment_data: AppointmentCreate, current_user: dict) -> Appointment:
        """
        Create a new appointment
        """
        try:
            # Set auth header once for all service calls
            auth_header = None
            if current_user:
                # Check for token in the Authorization header if it exists
                auth_token = current_user.get("token")
                if not auth_token and "authorization" in current_user:
                    # Extract from the Authorization header
                    auth_parts = current_user.get("authorization", "").split(" ")
                    if len(auth_parts) == 2 and auth_parts[0].lower() == "bearer":
                        auth_token = auth_parts[1]

                if auth_token:
                    auth_header = f"Bearer {auth_token}"
                    # Log for debugging
                    logger_service.info(f"Using auth token (first 10 chars): {auth_token[:10]}...")
                else:
                    logger_service.warning(f"No auth token found in current_user: {current_user.keys()}")

            # Validate that the provider exists
            provider_exists = await self.medecin_service.get_doctor_by_id(appointment_data.provider_id, auth_header)
            logger_service.info(f"Provider exists: {provider_exists}")
            if not provider_exists:
                logger_service.error(f"Provider {appointment_data.provider_id} not found")
                raise Exception(f"Provider {appointment_data.provider_id} not found")

            # Validate that the patient exists
            patient_exists = await self.patient_service.verify_patient_exists(appointment_data.patient_id, auth_header)
            if not patient_exists:
                logger_service.error(f"Patient {appointment_data.patient_id} not found")
                raise Exception(f"Patient {appointment_data.patient_id} not found")

            # Create a new appointment object
            appointment = Appointment(
                patient_id=appointment_data.patient_id,
                provider_id=appointment_data.provider_id,
                provider_type=appointment_data.provider_type,
                appointment_type=appointment_data.appointment_type,
                appointment_date=appointment_data.appointment_date,
                duration_minutes=appointment_data.duration_minutes,
                notes=appointment_data.notes,
                virtual=appointment_data.virtual,
                meeting_link=appointment_data.meeting_link,
            )

            # Convert to dict for database insertion
            appointment_dict = appointment.dict()

            # Insert into database using our MongoDB client
            appointment_data = self.mongodb_client.insert_appointment(appointment_dict)

            if appointment_data:
                # Get the newly created appointment with its ID
                appointment = Appointment(**appointment_data)

                # Send notification about the new appointment
                await self._notify_appointment_created(appointment)

                # Notify the doctor about the new appointment
                await self.medecin_service.notify_doctor_appointment(
                    doctor_id=appointment.provider_id,
                    appointment_data={
                        "appointment_id": appointment.appointment_id,
                        "patient_id": appointment.patient_id,
                        "appointment_date": appointment.appointment_date.isoformat(),
                        "duration_minutes": appointment.duration_minutes,
                        "notes": appointment.notes,
                    },
                    auth_header=auth_header,
                )

                # Notify the patient about the new appointment
                await self.patient_service.notify_patient_appointment(
                    patient_id=appointment.patient_id,
                    appointment_data={
                        "appointment_id": appointment.appointment_id,
                        "provider_id": appointment.provider_id,
                        "appointment_date": appointment.appointment_date.isoformat(),
                        "duration_minutes": appointment.duration_minutes,
                        "notes": appointment.notes,
                    },
                    auth_header=auth_header,
                )

                logger_service.info(f"Created appointment {appointment.appointment_id} for patient {appointment.patient_id}")
                return appointment
            else:
                logger_service.error("Failed to create appointment")
                raise Exception("Failed to create appointment")

        except Exception as e:
            logger_service.error(f"Error in create_appointment: {e!s}")
            raise

    async def get_appointment(self, appointment_id: str) -> Appointment | None:
        """
        Get a specific appointment by ID
        """
        try:
            # Use our MongoDB client to find the appointment
            appointment_data = self.mongodb_client.find_appointment_by_id(appointment_id)

            if not appointment_data:
                return None

            return Appointment(**appointment_data)

        except Exception as e:
            logger_service.error(f"Error in get_appointment: {e!s}")
            return None

    async def list_appointments(
        self,
        patient_id: str | None = None,
        provider_id: str | None = None,
        status: AppointmentStatus | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        page: int = 1,
        limit: int = 10,
    ) -> dict[str, Any]:
        """
        List appointments with optional filters and pagination
        """
        try:
            query = {}

            # Apply filters if provided
            if patient_id:
                query["patient_id"] = patient_id

            if provider_id:
                query["provider_id"] = provider_id

            if status:
                query["status"] = status

            if start_date or end_date:
                date_query = {}
                if start_date:
                    date_query["$gte"] = start_date
                if end_date:
                    date_query["$lte"] = end_date

                if date_query:
                    query["appointment_date"] = date_query

            # Use our MongoDB client to find appointments
            appointments = self.mongodb_client.find_appointments(query)

            # Apply manual pagination
            total = len(appointments)
            pages = (total + limit - 1) // limit if limit else 1

            # Calculate skip and limit
            skip = (page - 1) * limit
            paginated_appointments = appointments[skip : skip + limit]

            # Convert to Appointment objects
            appointment_objects = [Appointment(**doc) for doc in paginated_appointments]

            # Build response with pagination metadata
            result = {
                "items": appointment_objects,
                "total": total,
                "page": page,
                "limit": limit,
                "pages": pages,
            }

            return result

        except Exception as e:
            logger_service.error(f"Error in list_appointments: {e!s}")
            return {"items": [], "total": 0, "page": page, "limit": limit, "pages": 0}

    async def update_appointment(self, appointment_id: str, appointment_update: AppointmentUpdate) -> Appointment | None:
        """
        Update an existing appointment
        """
        try:
            # Get only non-None fields from the update
            update_data = {k: v for k, v in appointment_update.dict().items() if v is not None}

            if not update_data:
                # No fields to update
                return await self.get_appointment(appointment_id)

            # Update the appointment using our MongoDB client
            updated_data = self.mongodb_client.update_appointment(appointment_id, update_data)

            if not updated_data:
                return None

            updated_appointment = Appointment(**updated_data)

            # Send notification about the updated appointment if status changed
            if "status" in update_data:
                await self._notify_appointment_status_changed(updated_appointment, update_data["status"])

                # Notify doctor and patient about the status change
                if update_data["status"] == AppointmentStatus.CONFIRMED:
                    await self.medecin_service.notify_doctor_appointment(
                        doctor_id=updated_appointment.provider_id,
                        appointment_data={
                            "appointment_id": updated_appointment.appointment_id,
                            "status": "confirmed",
                            "message": "Appointment confirmed",
                        },
                    )

                    await self.patient_service.notify_patient_appointment(
                        patient_id=updated_appointment.patient_id,
                        appointment_data={
                            "appointment_id": updated_appointment.appointment_id,
                            "status": "confirmed",
                            "message": "Your appointment has been confirmed",
                        },
                    )

                elif update_data["status"] == AppointmentStatus.CANCELLED:
                    await self.medecin_service.notify_doctor_appointment(
                        doctor_id=updated_appointment.provider_id,
                        appointment_data={
                            "appointment_id": updated_appointment.appointment_id,
                            "status": "cancelled",
                            "message": "Appointment cancelled",
                        },
                    )

                    await self.patient_service.notify_patient_appointment(
                        patient_id=updated_appointment.patient_id,
                        appointment_data={
                            "appointment_id": updated_appointment.appointment_id,
                            "status": "cancelled",
                            "message": "Your appointment has been cancelled",
                        },
                    )

            return updated_appointment

        except Exception as e:
            logger_service.error(f"Error in update_appointment: {e!s}")
            return None

    async def process_appointment_request(self, patient_id: str, doctor_id: str, appointment_data: dict[str, Any]) -> str:
        """
        Process an appointment request from a patient
        """
        try:
            # Create appointment details
            requested_time = appointment_data.get("requested_time")
            reason = appointment_data.get("reason")

            # Parse the requested time
            try:
                appointment_date = datetime.fromisoformat(requested_time)
            except (ValueError, TypeError):
                logger_service.error(f"Invalid appointment time format: {requested_time}")
                return None

            # Create a new appointment
            new_appointment = Appointment(
                patient_id=patient_id,
                provider_id=doctor_id,
                provider_type=ProviderType.DOCTOR,
                appointment_type="consultation",  # Default type
                appointment_date=appointment_date,
                duration_minutes=30,  # Default duration
                notes=reason,
                status=AppointmentStatus.SCHEDULED,  # Start as scheduled
            )

            # Save to database
            appointment_dict = new_appointment.dict()
            result = await self.db.appointments.insert_one(appointment_dict)

            if not result.acknowledged:
                logger_service.error("Failed to create appointment from request")
                return None

            # Notify the doctor about the new appointment request
            self.rabbitmq_client.publish_message(
                exchange="medical.appointments",
                routing_key="appointment.request.received",
                message={
                    "appointment_id": new_appointment.appointment_id,
                    "patient_id": patient_id,
                    "doctor_id": doctor_id,
                    "requested_time": requested_time,
                    "reason": reason,
                    "status": "pending",
                },
            )

            # Create a notification for the doctor
            notification = AppointmentNotification(
                appointment_id=new_appointment.appointment_id,
                recipient_id=doctor_id,
                recipient_type="doctor",
                notification_type="appointment_request",
                message=f"New appointment request from patient for {requested_time}",
            )

            # Save notification
            await self.db.notifications.insert_one(notification.dict())

            logger_service.info(f"Processed appointment request: {new_appointment.appointment_id}")
            return new_appointment.appointment_id

        except Exception as e:
            logger_service.error(f"Error processing appointment request: {e!s}")
            return None

    async def respond_to_appointment(
        self,
        appointment_id: str,
        doctor_id: str,
        status: str,
        message: str | None = None,
    ) -> bool:
        """
        Handle doctor's response to appointment request (accept/reject)
        """
        try:
            # Verify the appointment exists and belongs to this doctor
            appointment = await self.get_appointment(appointment_id)

            if not appointment or appointment.provider_id != doctor_id:
                logger_service.warning(f"Doctor {doctor_id} attempted to respond to appointment {appointment_id} that doesn't exist or belong to them")
                return False

            # Update appointment status based on response
            new_status = AppointmentStatus.CONFIRMED if status.lower() == "accepted" else AppointmentStatus.CANCELLED

            # Update the appointment
            update_result = await self.db.appointments.update_one(
                {"appointment_id": appointment_id},
                {"$set": {"status": new_status, "updated_at": datetime.utcnow()}},
            )

            if not update_result.modified_count:
                return False

            # Get patient ID from appointment
            patient_id = appointment.patient_id

            # Send notification to patient about the response
            self.rabbitmq_client.notify_appointment_response(
                appointment_id=appointment_id,
                doctor_id=doctor_id,
                patient_id=patient_id,
                status=status,
                message=message,
            )

            # Create a notification for the patient
            notification = AppointmentNotification(
                appointment_id=appointment_id,
                recipient_id=patient_id,
                recipient_type="patient",
                notification_type=f"appointment_{status}",
                message=f"Your appointment request has been {status}" + (f": {message}" if message else ""),
            )

            # Save notification
            await self.db.notifications.insert_one(notification.dict())

            logger_service.info(f"Doctor {doctor_id} {status} appointment {appointment_id}")
            return True

        except Exception as e:
            logger_service.error(f"Error responding to appointment: {e!s}")
            return False

    async def cancel_appointment(self, appointment_id: str, cancellation_reason: str | None = None) -> bool:
        """
        Cancel an appointment
        """
        try:
            # Get the appointment first to have full data for notifications
            appointment = await self.get_appointment(appointment_id)

            if not appointment:
                return False

            # Update the appointment status to cancelled
            result = await self.db.appointments.find_one_and_update(
                {"appointment_id": appointment_id},
                {
                    "$set": {
                        "status": AppointmentStatus.CANCELLED,
                        "cancellation_reason": cancellation_reason,
                        "updated_at": datetime.utcnow(),
                    }
                },
                return_document=ReturnDocument.AFTER,
            )

            if not result:
                return False

            # Send cancellation notification
            cancelled_appointment = Appointment(**result)
            await self._notify_appointment_cancelled(cancelled_appointment, cancellation_reason)

            return True

        except Exception as e:
            logger_service.error(f"Error in cancel_appointment: {e!s}")
            return False

    async def get_available_slots(
        self,
        provider_id: str | None = None,
        provider_type: ProviderType | None = None,
        start_date: datetime = None,
        end_date: datetime = None,
        duration_minutes: int = 30,
    ) -> list[TimeSlot]:
        """
        Get available appointment slots for a provider or provider type
        """
        try:
            # Get provider schedules
            schedule_query = {}
            if provider_id:
                schedule_query["provider_id"] = provider_id
            if provider_type:
                schedule_query["provider_type"] = provider_type

            provider_schedules = []
            cursor = self.db.provider_schedules.find(schedule_query)

            async for doc in cursor:
                provider_schedules.append(ProviderSchedule(**doc))

            # Get existing appointments in the date range
            appointment_query = {
                "appointment_date": {"$gte": start_date, "$lte": end_date},
                "status": {"$nin": [AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW]},
            }

            if provider_id:
                appointment_query["provider_id"] = provider_id
            if provider_type:
                appointment_query["provider_type"] = provider_type

            existing_appointments = []
            cursor = self.db.appointments.find(appointment_query)

            async for doc in cursor:
                existing_appointments.append(Appointment(**doc))

            # Generate available time slots based on schedules and existing appointments
            available_slots = await self._generate_available_slots(
                provider_schedules,
                existing_appointments,
                start_date,
                end_date,
                duration_minutes,
            )

            return available_slots

        except Exception as e:
            logger_service.error(f"Error in get_available_slots: {e!s}")
            return []

    async def get_provider_schedule(self, provider_id: str) -> ProviderSchedule | None:
        """
        Get a provider's schedule configuration
        """
        try:
            schedule_data = await self.db.provider_schedules.find_one({"provider_id": provider_id})

            if not schedule_data:
                return None

            return ProviderSchedule(**schedule_data)

        except Exception as e:
            logger_service.error(f"Error in get_provider_schedule: {e!s}")
            return None

    async def update_provider_schedule(self, provider_schedule: ProviderSchedule) -> ProviderSchedule | None:
        """
        Update a provider's schedule configuration
        """
        try:
            # Update the provider's schedule in database
            schedule_dict = provider_schedule.dict()
            schedule_dict["updated_at"] = datetime.utcnow()

            result = await self.db.provider_schedules.find_one_and_update(
                {"provider_id": provider_schedule.provider_id},
                {"$set": schedule_dict},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )

            # Notify about schedule update
            self.rabbitmq_client.notify_provider_schedule_update(
                provider_id=provider_schedule.provider_id,
                provider_type=provider_schedule.provider_type,
            )

            return ProviderSchedule(**result)

        except Exception as e:
            logger_service.error(f"Error in update_provider_schedule: {e!s}")
            return None

    async def create_appointment_reminder(self, appointment_id: str) -> bool:
        """
        Create a reminder for an upcoming appointment
        """
        try:
            appointment = await self.get_appointment(appointment_id)

            if not appointment or appointment.status != AppointmentStatus.CONFIRMED:
                return False

            # Check if we already sent a reminder for this appointment
            existing_reminder = await self.db.notifications.find_one(
                {
                    "appointment_id": appointment_id,
                    "notification_type": "appointment_reminder",
                }
            )

            if existing_reminder:
                return True  # Already sent

            # Create patient reminder
            patient_notification = AppointmentNotification(
                appointment_id=appointment_id,
                recipient_id=appointment.patient_id,
                recipient_type="patient",
                notification_type="appointment_reminder",
                message=f"Reminder: You have an appointment scheduled for {appointment.appointment_date.isoformat()}",
            )

            # Create provider reminder
            provider_notification = AppointmentNotification(
                appointment_id=appointment_id,
                recipient_id=appointment.provider_id,
                recipient_type="provider",
                notification_type="appointment_reminder",
                message=f"Reminder: You have an appointment scheduled for {appointment.appointment_date.isoformat()}",
            )

            # Save notifications
            await self.db.notifications.insert_one(patient_notification.dict())
            await self.db.notifications.insert_one(provider_notification.dict())

            # Send via RabbitMQ
            formatted_time = appointment.appointment_date.strftime("%Y-%m-%d %H:%M")

            # Send to patient
            self.rabbitmq_client.send_appointment_reminder(
                appointment_id=appointment_id,
                recipient_id=appointment.patient_id,
                recipient_type="patient",
                appointment_time=formatted_time,
                provider_name=f"Provider {appointment.provider_id}",  # In real app, get actual name
            )

            # Send to provider
            self.rabbitmq_client.send_appointment_reminder(
                appointment_id=appointment_id,
                recipient_id=appointment.provider_id,
                recipient_type=appointment.provider_type,
                appointment_time=formatted_time,
                provider_name=f"Patient {appointment.patient_id}",  # In real app, get actual name
            )

            return True

        except Exception as e:
            logger_service.error(f"Error creating appointment reminder: {e!s}")
            return False

    async def _generate_available_slots(
        self,
        provider_schedules: list[ProviderSchedule],
        existing_appointments: list[Appointment],
        start_date: datetime,
        end_date: datetime,
        duration_minutes: int,
    ) -> list[TimeSlot]:
        """
        Generate available time slots based on schedules and existing appointments
        """
        available_slots = []

        # Implementation would generate slots based on provider schedules and existing appointments
        # This is a simplified example and would need to be expanded

        for schedule in provider_schedules:
            provider_id = schedule.provider_id
            provider_type = schedule.provider_type

            # Generate slots for each day in range
            current_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            while current_date <= end_date:
                day_of_week = str(current_date.weekday())

                # If provider works this day
                if day_of_week in schedule.work_hours:
                    work_hours = schedule.work_hours[day_of_week]

                    # Generate slots for this day's working hours
                    day_start = current_date.replace(hour=work_hours.start, minute=0)
                    day_end = current_date.replace(hour=work_hours.end, minute=0)

                    # Check for breaks
                    break_start = None
                    break_end = None
                    if work_hours.break_start is not None and work_hours.break_end is not None:
                        break_start = current_date.replace(hour=work_hours.break_start, minute=0)
                        break_end = current_date.replace(hour=work_hours.break_end, minute=0)

                    # Generate slots
                    slot_time = day_start
                    while slot_time < day_end:
                        slot_end = slot_time + timedelta(minutes=duration_minutes)

                        # Skip slots during break time
                        if break_start is None or slot_time >= break_end or slot_end <= break_start:
                            # Check if slot overlaps with existing appointments
                            slot_available = True
                            for appt in existing_appointments:
                                if appt.provider_id == provider_id and appt.appointment_date <= slot_time < (appt.appointment_date + timedelta(minutes=appt.duration_minutes)):
                                    slot_available = False
                                    break

                            if slot_available:
                                available_slots.append(
                                    TimeSlot(
                                        start_time=slot_time,
                                        end_time=slot_end,
                                        provider_id=provider_id,
                                        provider_type=provider_type,
                                        is_available=True,
                                    )
                                )

                        # Move to next slot
                        slot_time += timedelta(minutes=duration_minutes)

                # Move to next day
                current_date += timedelta(days=1)

        return available_slots

    async def _notify_appointment_created(self, appointment: Appointment) -> None:
        """
        Send notifications about a new appointment
        """
        try:
            logger_service.info(f"Sending notification for new appointment {appointment.appointment_id}")

            # Notify about the new appointment
            self.rabbitmq_client.notify_appointment_created(
                {
                    "appointment_id": appointment.appointment_id,
                    "patient_id": appointment.patient_id,
                    "provider_id": appointment.provider_id,
                    "provider_type": appointment.provider_type,
                    "appointment_date": appointment.appointment_date.isoformat(),
                    "duration_minutes": appointment.duration_minutes,
                    "status": appointment.status,
                }
            )

        except Exception as e:
            logger_service.error(f"Error sending appointment creation notification: {e!s}")

    async def _notify_appointment_status_changed(self, appointment: Appointment, new_status: AppointmentStatus) -> None:
        """
        Send notifications about an appointment status change
        """
        try:
            logger_service.info(f"Sending notification for appointment {appointment.appointment_id} status change to {new_status}")

            # Notify about the status change
            self.rabbitmq_client.notify_appointment_status_change(
                appointment_id=appointment.appointment_id,
                status=new_status,
                provider_id=appointment.provider_id,
                patient_id=appointment.patient_id,
            )

        except Exception as e:
            logger_service.error(f"Error sending appointment status change notification: {e!s}")

    async def _notify_appointment_cancelled(self, appointment: Appointment, reason: str | None = None) -> None:
        """
        Send notifications about a cancelled appointment
        """
        try:
            logger_service.info(f"Sending notification for cancelled appointment {appointment.appointment_id}")

            # Prepare appointment data
            appointment_data = {
                "appointment_id": appointment.appointment_id,
                "patient_id": appointment.patient_id,
                "provider_id": appointment.provider_id,
                "provider_type": appointment.provider_type,
                "appointment_date": appointment.appointment_date.isoformat(),
                "status": "cancelled",
            }

            # Send cancellation notification
            self.rabbitmq_client.notify_appointment_cancelled(appointment_data, reason)

        except Exception as e:
            logger_service.error(f"Error sending appointment cancellation notification: {e!s}")

    async def find_appointments_by_patient(self, patient_id: str) -> list[Appointment]:
        """
        Find all appointments for a specific patient
        """
        try:
            # Check if patient exists
            patient_exists = await self.patient_service.verify_patient_exists(patient_id)
            if not patient_exists:
                logger_service.warning(f"Patient {patient_id} not found when looking for appointments")
                return []

            # Use MongoDB client to find appointments by patient
            appointments_data = self.mongodb_client.find_appointments_by_patient(patient_id)

            # Convert to Appointment objects
            appointments = [Appointment(**doc) for doc in appointments_data]

            return appointments

        except Exception as e:
            logger_service.error(f"Error finding appointments for patient {patient_id}: {e!s}")
            return []

    async def find_appointments_by_provider(self, provider_id: str) -> list[Appointment]:
        """
        Find all appointments for a specific provider (doctor)
        """
        try:
            # Check if provider exists
            provider_info = await self.medecin_service.get_doctor_by_id(provider_id)
            if not provider_info:
                logger_service.warning(f"Provider {provider_id} not found when looking for appointments")
                return []

            # Use MongoDB client to find appointments by provider
            appointments_data = self.mongodb_client.find_appointments_by_provider(provider_id)

            # Convert to Appointment objects
            appointments = [Appointment(**doc) for doc in appointments_data]

            return appointments

        except Exception as e:
            logger_service.error(f"Error finding appointments for provider {provider_id}: {e!s}")
            return []

    async def close(self):
        """
        Close connections and clean up
        """
        try:
            await self.client.aclose()
            self.mongodb_client.close()
        except Exception as e:
            logger_service.error(f"Error closing connections: {e!s}")
