import json
from datetime import datetime

from services.logger_service import logger_service
from services.mongodb_client import MongoDBClient
from services.rabbitmq_client import RabbitMQClient

from config import Config


def handle_medical_update(ch, method, properties, body):
    """Handle medical updates for patients"""
    try:
        # Parse message
        message = json.loads(body)
        logger_service.info(f"Received medical update: {message}")

        # Store in database
        mongodb_client = MongoDBClient(Config)
        mongodb_client.db.medical_updates.insert_one(
            {
                "update_type": method.routing_key.split(".")[-1],
                "patient_id": message.get("patient_id"),
                "timestamp": datetime.utcnow().isoformat(),
                "data": message.get("data", {}),
                "raw_update": message,
            }
        )

        # Acknowledge message
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        logger_service.error(f"Error processing medical update: {e}")
        # Negative acknowledgment with requeue=True to retry later
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def handle_appointment_response(ch, method, properties, body):
    """Handle responses to appointment requests"""
    try:
        # Parse message
        message = json.loads(body)
        logger_service.info(f"Received appointment response: {message}")

        # Store in database
        mongodb_client = MongoDBClient(Config)
        mongodb_client.db.appointment_responses.insert_one(
            {
                "appointment_id": message.get("appointment_id"),
                "patient_id": message.get("patient_id"),
                "doctor_id": message.get("doctor_id"),
                "status": message.get("status"),
                "message": message.get("message"),
                "received_at": datetime.utcnow().isoformat(),
                "raw_response": message,
            }
        )

        # Also update the appointment request in the database
        mongodb_client.db.appointment_requests.update_one(
            {"appointment_id": message.get("appointment_id")},
            {
                "$set": {
                    "status": message.get("status"),
                    "response_message": message.get("message"),
                    "response_received_at": datetime.utcnow().isoformat(),
                }
            },
        )

        # Acknowledge message
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        logger_service.error(f"Error processing appointment response: {e}")
        # Negative acknowledgment with requeue=True to retry later
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def handle_prescription_notification(ch, method, properties, body):
    """Handle prescription notifications"""
    try:
        # Parse message
        message = json.loads(body)
        logger_service.info(f"Received prescription notification: {message}")

        # Store in database
        mongodb_client = MongoDBClient(Config)
        mongodb_client.db.prescription_notifications.insert_one(
            {
                "prescription_id": message.get("prescription_id"),
                "patient_id": message.get("patient_id"),
                "action": message.get("action"),
                "received_at": datetime.utcnow().isoformat(),
                "raw_notification": message,
            }
        )

        # Also update the prescription in the database if it exists
        if mongodb_client.db.prescriptions.find_one(
            {"prescription_id": message.get("prescription_id")}
        ):
            mongodb_client.db.prescriptions.update_one(
                {"prescription_id": message.get("prescription_id")},
                {
                    "$set": {
                        "status": message.get("action"),
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                },
            )
        else:
            # Create a new prescription record
            mongodb_client.db.prescriptions.insert_one(
                {
                    "prescription_id": message.get("prescription_id"),
                    "patient_id": message.get("patient_id"),
                    "doctor_id": message.get("doctor_id", "unknown"),
                    "status": message.get("action"),
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                }
            )

        # Acknowledge message
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        logger_service.error(f"Error processing prescription notification: {e}")
        # Negative acknowledgment with requeue=True to retry later
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def main():
    """Main consumer function"""
    try:
        # Initialize clients
        rabbitmq_client = RabbitMQClient(Config)

        # Set up consumers for different queues

        # Medical updates
        rabbitmq_client.consume_messages(
            "patients.medical_updates", handle_medical_update
        )

        # Appointment responses
        rabbitmq_client.consume_messages(
            "patients.appointments", handle_appointment_response
        )

        # Prescription notifications
        rabbitmq_client.consume_messages(
            "patients.prescriptions", handle_prescription_notification
        )

        # Start consuming (this is a blocking call)
        logger_service.info("Starting to consume messages. Press CTRL+C to exit.")
        rabbitmq_client.channel.start_consuming()

    except KeyboardInterrupt:
        logger_service.info("Consumer stopped by user.")
    except Exception as e:
        logger_service.error(f"Consumer error: {e}")


if __name__ == "__main__":
    main()
