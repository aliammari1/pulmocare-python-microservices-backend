import asyncio
import json
from typing import Any

import aio_pika

from config import Config
from models.appointment import AppointmentStatus
from services.appointment_service import AppointmentService
from services.logger_service import logger_service


class AppointmentConsumer:
    """Consumer for appointment-related messages from RabbitMQ"""

    def __init__(self, config: Config):
        self.config = config
        self.connection = None
        self.channel = None
        self.appointment_service = AppointmentService()
        self.handlers = {
            "appointment.request.created": self._handle_appointment_request,
            "appointment.response.accepted": self._handle_appointment_response,
            "appointment.response.rejected": self._handle_appointment_response,
            "appointment.status.updated": self._handle_appointment_status_update,
            "appointment.cancelled": self._handle_appointment_cancelled,
            "appointment.reminder.needed": self._handle_appointment_reminder,
            "provider.schedule.updated": self._handle_provider_schedule_updated,
        }

    async def connect(self):
        """Connect to RabbitMQ server"""
        try:
            # Create connection string
            connection_string = f"amqp://{self.config.RABBITMQ_USER}:{self.config.RABBITMQ_PASS}@{self.config.RABBITMQ_HOST}:{self.config.RABBITMQ_PORT}/{self.config.RABBITMQ_VHOST}"

            # Connect using aio_pika
            self.connection = await aio_pika.connect_robust(connection_string, heartbeat=600)

            # Create channel
            self.channel = await self.connection.channel()

            # Ensure exchanges exist
            await self.channel.declare_exchange(name="medical.appointments", type="topic", durable=True)

            await self.channel.declare_exchange(name="medical.notifications", type="topic", durable=True)

            await self.channel.declare_exchange(name="medical.events", type="topic", durable=True)

            # Create and bind queues
            await self._setup_queues()

            logger_service.info("Connected to RabbitMQ and setup queues")

        except Exception as e:
            logger_service.error(f"Failed to connect to RabbitMQ: {e!s}")
            raise

    async def _setup_queues(self):
        """Set up queues and bindings for appointment messages"""
        # Main appointments queue
        await self.channel.declare_queue(name="appointment.requests", durable=True)

        await self.channel.declare_queue(name="appointment.responses", durable=True)

        await self.channel.declare_queue(name="appointment.status.updates", durable=True)

        await self.channel.declare_queue(name="appointment.reminders", durable=True)

        await self.channel.declare_queue(name="provider.schedule.updates", durable=True)

        # Bind queues to exchanges with routing keys
        bindings = [
            # Appointment requests
            ("medical.appointments", "appointment.requests", "appointment.request.#"),
            # Appointment responses (accept/reject)
            ("medical.appointments", "appointment.responses", "appointment.response.#"),
            # Status updates (confirmed, completed, etc.)
            (
                "medical.appointments",
                "appointment.status.updates",
                "appointment.status.#",
            ),
            # Reminders
            ("medical.appointments", "appointment.reminders", "appointment.reminder.#"),
            # Schedule updates
            (
                "medical.appointments",
                "provider.schedule.updates",
                "provider.schedule.#",
            ),
        ]

        for exchange_name, queue_name, routing_key in bindings:
            exchange = await self.channel.get_exchange(exchange_name)
            queue = await self.channel.get_queue(queue_name)
            await queue.bind(exchange, routing_key)

        # Set up consumers
        for queue_name in [
            "appointment.requests",
            "appointment.responses",
            "appointment.status.updates",
            "appointment.reminders",
            "provider.schedule.updates",
        ]:
            queue = await self.channel.get_queue(queue_name)
            await queue.consume(self._process_message)

    async def _process_message(self, message):
        """Process incoming messages"""
        routing_key = message.routing_key

        try:
            body = message.body.decode("utf-8")
            data = json.loads(body)
            logger_service.info(f"Received message with routing key: {routing_key}")

            # Find appropriate handler based on routing key
            handler = None
            for key, h in self.handlers.items():
                if routing_key.startswith(key):
                    handler = h
                    break

            if handler:
                await handler(data)
                logger_service.info(f"Successfully processed message with routing key: {routing_key}")
            else:
                logger_service.warning(f"No handler for routing key: {routing_key}")

            # Acknowledge message
            await message.ack()

        except json.JSONDecodeError:
            logger_service.error(f"Invalid JSON in message: {body}")
            # Reject malformed messages
            await message.reject(requeue=False)

        except Exception as e:
            logger_service.error(f"Error processing message: {e!s}")
            # Negative acknowledgment, requeue for retry
            await message.nack(requeue=True)

    async def start_consuming(self):
        """Start consuming messages"""
        if not self.connection or not self.channel:
            await self.connect()

        logger_service.info("Starting to consume appointment messages")

    async def stop_consuming(self):
        """Stop consuming messages and close connection"""
        if self.channel:
            await self.channel.close()

        if self.connection:
            await self.connection.close()

        logger_service.info("Stopped consuming messages and closed connections")

    # Message handlers
    async def _handle_appointment_request(self, message: dict[str, Any]):
        """Handle appointment creation request messages"""
        try:
            logger_service.info(f"Processing appointment request: {message}")

            # Extract required data
            patient_id = message.get("patient_id")
            doctor_id = message.get("doctor_id")
            appointment_data = message.get("appointment_data", {})

            if not patient_id or not doctor_id or not appointment_data:
                logger_service.error("Missing required fields in appointment request")
                return

            # Process the appointment request
            appointment_id = await self.appointment_service.process_appointment_request(
                patient_id=patient_id,
                doctor_id=doctor_id,
                appointment_data=appointment_data,
            )

            if appointment_id:
                logger_service.info(f"Created appointment {appointment_id} from request")
            else:
                logger_service.error("Failed to create appointment from request")

        except Exception as e:
            logger_service.error(f"Error processing appointment request: {e!s}")
            raise

    async def _handle_appointment_response(self, message: dict[str, Any]):
        """Handle doctor responses to appointment requests (accept/reject)"""
        try:
            logger_service.info(f"Processing appointment response: {message}")

            # Extract required data
            appointment_id = message.get("appointment_id")
            doctor_id = message.get("doctor_id")
            status = message.get("status")
            response_message = message.get("message")

            if not appointment_id or not doctor_id or not status:
                logger_service.error("Missing required fields in appointment response")
                return

            # Update appointment based on response
            result = await self.appointment_service.respond_to_appointment(
                appointment_id=appointment_id,
                doctor_id=doctor_id,
                status=status,
                message=response_message,
            )

            if result:
                logger_service.info(f"Processed {status} response for appointment {appointment_id}")
            else:
                logger_service.error(f"Failed to process {status} response for appointment {appointment_id}")

        except Exception as e:
            logger_service.error(f"Error processing appointment response: {e!s}")
            raise

    async def _handle_appointment_status_update(self, message: dict[str, Any]):
        """Handle appointment status updates"""
        try:
            logger_service.info(f"Processing appointment status update: {message}")

            # Extract required data
            appointment_id = message.get("appointment_id")
            new_status = message.get("status")

            if not appointment_id or not new_status:
                logger_service.error("Missing required fields in status update")
                return

            # Update appointment status
            try:
                status_enum = AppointmentStatus(new_status)
            except ValueError:
                logger_service.error(f"Invalid appointment status: {new_status}")
                return

            result = await self.appointment_service.update_appointment(
                appointment_id=appointment_id,
                appointment_update={"status": status_enum},
            )

            if result:
                logger_service.info(f"Updated status for appointment {appointment_id} to {new_status}")
            else:
                logger_service.error(f"Failed to update status for appointment {appointment_id}")

        except Exception as e:
            logger_service.error(f"Error processing status update: {e!s}")
            raise

    async def _handle_appointment_cancelled(self, message: dict[str, Any]):
        """Handle appointment cancellation messages"""
        try:
            logger_service.info(f"Processing appointment cancellation: {message}")

            # Extract required data
            appointment_id = message.get("appointment_id")
            reason = message.get("cancellation_reason")

            if not appointment_id:
                logger_service.error("Missing appointment_id in cancellation message")
                return

            # Cancel the appointment
            result = await self.appointment_service.cancel_appointment(appointment_id=appointment_id, cancellation_reason=reason)

            if result:
                logger_service.info(f"Cancelled appointment {appointment_id}")
            else:
                logger_service.error(f"Failed to cancel appointment {appointment_id}")

        except Exception as e:
            logger_service.error(f"Error processing appointment cancellation: {e!s}")
            raise

    async def _handle_appointment_reminder(self, message: dict[str, Any]):
        """Handle appointment reminder messages"""
        try:
            logger_service.info(f"Processing appointment reminder: {message}")

            # Extract required data
            appointment_id = message.get("appointment_id")

            if not appointment_id:
                logger_service.error("Missing appointment_id in reminder message")
                return

            # Create and send a reminder
            result = await self.appointment_service.create_appointment_reminder(appointment_id)

            if result:
                logger_service.info(f"Sent reminder for appointment {appointment_id}")
            else:
                logger_service.error(f"Failed to send reminder for appointment {appointment_id}")

        except Exception as e:
            logger_service.error(f"Error processing appointment reminder: {e!s}")
            raise

    async def _handle_provider_schedule_updated(self, message: dict[str, Any]):
        """Handle provider schedule update messages"""
        try:
            logger_service.info(f"Processing provider schedule update: {message}")

            # Extract provider information
            provider_id = message.get("provider_id")

            if not provider_id:
                logger_service.error("Missing provider_id in schedule update message")
                return

            # Just log the update - actual implementation would update cached schedule information
            logger_service.info(f"Updated schedule for provider {provider_id}")

        except Exception as e:
            logger_service.error(f"Error processing provider schedule update: {e!s}")
            raise


if __name__ == "__main__":
    config = Config()
    consumer = AppointmentConsumer(config)
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(consumer.start_consuming())
        # Keep running until interrupted
        loop.run_forever()
    except KeyboardInterrupt:
        loop.run_until_complete(consumer.stop_consuming())
    finally:
        loop.close()
