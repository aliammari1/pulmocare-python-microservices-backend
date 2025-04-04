import json
import threading
from datetime import datetime
from typing import Any, Dict

from services.logger_service import logger_service
from services.mongodb_client import MongoDBClient
from services.rabbitmq_client import RabbitMQClient
from services.redis_client import RedisClient

from config import Config


class MessageConsumer:
    """Consumer for processing messages from RabbitMQ queues"""

    def __init__(
        self, config: Config, mongodb_client: MongoDBClient, redis_client: RedisClient
    ):
        """Initialize the message consumer with dependencies"""
        self.config = config
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client
        self.rabbitmq_client = RabbitMQClient(config)
        self.consumers = []

    def start_consumers(self):
        """Start consumers for all relevant queues"""
        self._start_consumer("ordonnances.created", self._handle_prescription_created)
        self._start_consumer(
            "ordonnances.notifications", self._handle_prescription_notification
        )
        self._start_consumer("patient.prescriptions", self._handle_patient_prescription)
        self._start_consumer("doctor.prescriptions", self._handle_doctor_prescription)

    def _start_consumer(self, queue_name: str, callback):
        """Start a consumer for a specific queue in a separate thread"""
        consumer_thread = threading.Thread(
            target=self._consume, args=(queue_name, callback), daemon=True
        )
        self.consumers.append(consumer_thread)
        consumer_thread.start()
        logger_service.info(f"Started consumer for {queue_name}")

    def _consume(self, queue_name: str, callback):
        """Consume messages from the specified queue"""
        try:
            # Create a separate RabbitMQ client for each consumer
            rabbit_client = RabbitMQClient(self.config)
            rabbit_client.consume_messages(queue_name, callback)
        except Exception as e:
            logger_service.error(f"Error in consumer for {queue_name}: {str(e)}")

    def _handle_prescription_created(self, channel, method, properties, body):
        """Handle prescription created messages"""
        try:
            message = json.loads(body)
            prescription_id = message.get("prescription_id")

            logger_service.info(f"Processing prescription creation: {prescription_id}")

            # Acknowledge message immediately to prevent redelivery
            channel.basic_ack(delivery_tag=method.delivery_tag)

            # Process the prescription
            self._process_prescription_creation(prescription_id, message)
        except Exception as e:
            logger_service.error(f"Error processing prescription creation: {str(e)}")
            # Acknowledge the message even on error to prevent redelivery loops
            channel.basic_ack(delivery_tag=method.delivery_tag)

    def _handle_prescription_notification(self, channel, method, properties, body):
        """Handle prescription notification messages"""
        try:
            message = json.loads(body)
            prescription_id = message.get("prescription_id")
            event = message.get("event")

            logger_service.info(
                f"Received notification for prescription {prescription_id}: {event}"
            )

            # Acknowledge message immediately
            channel.basic_ack(delivery_tag=method.delivery_tag)

            # Process the notification
            self._process_prescription_notification(prescription_id, event, message)
        except Exception as e:
            logger_service.error(
                f"Error processing prescription notification: {str(e)}"
            )
            channel.basic_ack(delivery_tag=method.delivery_tag)

    def _handle_patient_prescription(self, channel, method, properties, body):
        """Handle patient prescription messages"""
        try:
            message = json.loads(body)
            prescription_id = message.get("prescription_id")
            patient_id = message.get("patient_id")
            action = message.get("action")

            logger_service.info(
                f"Processing patient prescription action: {action} for patient {patient_id}"
            )

            # Acknowledge message immediately
            channel.basic_ack(delivery_tag=method.delivery_tag)

            # Process the patient prescription action
            self._process_patient_prescription(
                prescription_id, patient_id, action, message
            )
        except Exception as e:
            logger_service.error(f"Error processing patient prescription: {str(e)}")
            channel.basic_ack(delivery_tag=method.delivery_tag)

    def _handle_doctor_prescription(self, channel, method, properties, body):
        """Handle doctor prescription messages"""
        try:
            message = json.loads(body)
            prescription_id = message.get("prescription_id")
            doctor_id = message.get("doctor_id")
            action = message.get("action")

            logger_service.info(
                f"Processing doctor prescription action: {action} for doctor {doctor_id}"
            )

            # Acknowledge message immediately
            channel.basic_ack(delivery_tag=method.delivery_tag)

            # Process the doctor prescription action
            self._process_doctor_prescription(
                prescription_id, doctor_id, action, message
            )
        except Exception as e:
            logger_service.error(f"Error processing doctor prescription: {str(e)}")
            channel.basic_ack(delivery_tag=method.delivery_tag)

    def _process_prescription_creation(
        self, prescription_id: str, message: Dict[str, Any]
    ):
        """Process a prescription creation event"""
        try:
            doctor_id = message.get("doctor_id")
            patient_id = message.get("patient_id")

            # Check if prescription exists in our database
            prescription = self.mongodb_client.db.ordonnances.find_one(
                {"_id": prescription_id}
            )

            if not prescription:
                # Prescription doesn't exist, store it
                logger_service.info(
                    f"New prescription {prescription_id} received, storing it"
                )

                # Create prescription document
                prescription_data = {
                    "_id": prescription_id,
                    "doctor_id": doctor_id,
                    "patient_id": patient_id,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                    "status": "created",
                    "source": "external",
                    "raw_message": message,
                }

                # Store in database
                self.mongodb_client.db.ordonnances.insert_one(prescription_data)

                # Notify other services about the prescription being received
                self.rabbitmq_client.publish_message(
                    exchange="medical.events",
                    routing_key="prescription.received",
                    message={
                        "prescription_id": prescription_id,
                        "doctor_id": doctor_id,
                        "patient_id": patient_id,
                        "event": "prescription_received",
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )
            else:
                logger_service.info(
                    f"Prescription {prescription_id} already exists, updating"
                )

                # Update the existing prescription
                self.mongodb_client.db.ordonnances.update_one(
                    {"_id": prescription_id},
                    {
                        "$set": {
                            "updated_at": datetime.utcnow(),
                            "last_message": message,
                        }
                    },
                )

            logger_service.info(
                f"Successfully processed prescription {prescription_id}"
            )

        except Exception as e:
            logger_service.error(f"Error in _process_prescription_creation: {str(e)}")

    def _process_prescription_notification(
        self, prescription_id: str, event: str, message: Dict[str, Any]
    ):
        """Process a prescription notification"""
        try:
            # Update prescription status based on the event
            if event == "prescription_dispensed":
                # Update prescription to dispensed status
                self.mongodb_client.db.ordonnances.update_one(
                    {"_id": prescription_id},
                    {
                        "$set": {
                            "status": "dispensed",
                            "dispensed_at": datetime.utcnow(),
                            "pharmacy_id": message.get("pharmacy_id"),
                            "updated_at": datetime.utcnow(),
                        }
                    },
                )

                # Could notify patient via messaging service, email, etc.

            elif event == "prescription_cancelled":
                # Update prescription to cancelled status
                self.mongodb_client.db.ordonnances.update_one(
                    {"_id": prescription_id},
                    {
                        "$set": {
                            "status": "cancelled",
                            "cancelled_at": datetime.utcnow(),
                            "cancelled_by": message.get("cancelled_by"),
                            "cancellation_reason": message.get("reason"),
                            "updated_at": datetime.utcnow(),
                        }
                    },
                )

            # Store notification for audit trail
            self.mongodb_client.db.prescription_notifications.insert_one(
                {
                    "prescription_id": prescription_id,
                    "event": event,
                    "message": message,
                    "processed_at": datetime.utcnow(),
                }
            )

            logger_service.info(
                f"Processed notification for prescription {prescription_id}: {event}"
            )

        except Exception as e:
            logger_service.error(
                f"Error processing prescription notification: {str(e)}"
            )

    def _process_patient_prescription(
        self,
        prescription_id: str,
        patient_id: str,
        action: str,
        message: Dict[str, Any],
    ):
        """Process a patient prescription action"""
        try:
            # Handle different patient actions
            if action == "viewed":
                # Update prescription view stats
                self.mongodb_client.db.prescription_stats.update_one(
                    {"prescription_id": prescription_id},
                    {
                        "$inc": {"patient_view_count": 1},
                        "$push": {
                            "patient_views": {
                                "timestamp": datetime.utcnow(),
                                "patient_id": patient_id,
                            }
                        },
                    },
                    upsert=True,
                )

            elif action == "requested_renewal":
                # Handle renewal request
                self.mongodb_client.db.prescription_renewals.insert_one(
                    {
                        "prescription_id": prescription_id,
                        "patient_id": patient_id,
                        "requested_at": datetime.utcnow(),
                        "status": "pending",
                        "message": message.get("message"),
                    }
                )

                # Notify doctor about renewal request
                doctor_id = message.get("doctor_id")
                if doctor_id:
                    self.rabbitmq_client.notify_doctor_prescription(
                        prescription_id, doctor_id, "renewal_requested"
                    )

            logger_service.info(
                f"Processed patient action {action} for prescription {prescription_id}"
            )

        except Exception as e:
            logger_service.error(
                f"Error processing patient prescription action: {str(e)}"
            )

    def _process_doctor_prescription(
        self, prescription_id: str, doctor_id: str, action: str, message: Dict[str, Any]
    ):
        """Process a doctor prescription action"""
        try:
            # Handle different doctor actions
            if action == "renewed":
                # Create new prescription based on renewal
                new_prescription_id = (
                    f"renewed-{prescription_id}-{int(datetime.utcnow().timestamp())}"
                )

                # Copy original prescription data with updates
                original = self.mongodb_client.db.ordonnances.find_one(
                    {"_id": prescription_id}
                )
                if original:
                    # Create new prescription with updated data
                    new_prescription = {
                        "_id": new_prescription_id,
                        "doctor_id": doctor_id,
                        "patient_id": original.get("patient_id"),
                        "original_prescription_id": prescription_id,
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                        "status": "created",
                        "medications": message.get(
                            "medications", original.get("medications", [])
                        ),
                        "instructions": message.get(
                            "instructions", original.get("instructions")
                        ),
                        "diagnosis": original.get("diagnosis"),
                        "renewal_count": (original.get("renewal_count", 0) + 1),
                    }

                    # Store new prescription
                    self.mongodb_client.db.ordonnances.insert_one(new_prescription)

                    # Update renewal request status
                    self.mongodb_client.db.prescription_renewals.update_one(
                        {"prescription_id": prescription_id, "status": "pending"},
                        {
                            "$set": {
                                "status": "approved",
                                "approved_at": datetime.utcnow(),
                                "new_prescription_id": new_prescription_id,
                            }
                        },
                    )

                    # Notify patient about renewal
                    patient_id = original.get("patient_id")
                    if patient_id:
                        self.rabbitmq_client.notify_patient_prescription(
                            new_prescription_id, patient_id, "renewal_approved"
                        )

                    logger_service.info(
                        f"Created renewed prescription {new_prescription_id}"
                    )
                else:
                    logger_service.warning(
                        f"Cannot renew prescription {prescription_id} - original not found"
                    )

            elif action == "cancelled":
                # Update prescription to cancelled status
                self.mongodb_client.db.ordonnances.update_one(
                    {"_id": prescription_id},
                    {
                        "$set": {
                            "status": "cancelled",
                            "cancelled_at": datetime.utcnow(),
                            "cancelled_by": doctor_id,
                            "cancellation_reason": message.get("reason"),
                            "updated_at": datetime.utcnow(),
                        }
                    },
                )

                # If there was a pending renewal request, update it
                self.mongodb_client.db.prescription_renewals.update_one(
                    {"prescription_id": prescription_id, "status": "pending"},
                    {
                        "$set": {
                            "status": "rejected",
                            "rejected_at": datetime.utcnow(),
                            "rejection_reason": message.get("reason"),
                        }
                    },
                )

                # Notify patient about cancellation
                patient_id = message.get("patient_id")
                if patient_id:
                    self.rabbitmq_client.notify_patient_prescription(
                        prescription_id, patient_id, "cancelled"
                    )

            logger_service.info(
                f"Processed doctor action {action} for prescription {prescription_id}"
            )

        except Exception as e:
            logger_service.error(
                f"Error processing doctor prescription action: {str(e)}"
            )

    def stop(self):
        """Stop all consumers"""
        if self.rabbitmq_client:
            self.rabbitmq_client.close()
            logger_service.info("RabbitMQ connection closed")
