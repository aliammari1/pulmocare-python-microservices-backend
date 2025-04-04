import json
from datetime import datetime

from services.logger_service import logger_service
from services.mongodb_client import MongoDBClient
from services.rabbitmq_client import RabbitMQClient

from config import Config


def handle_appointment_request(ch, method, properties, body):
    """Handle incoming appointment requests"""
    try:
        # Parse message
        message = json.loads(body)
        logger_service.info(f"Received appointment request: {message}")

        # Store in database
        mongodb_client = MongoDBClient(Config)
        mongodb_client.db.appointment_requests.insert_one(
            {
                "appointment_id": message.get("appointment_id"),
                "patient_id": message.get("patient_id"),
                "doctor_id": message.get("doctor_id"),
                "requested_time": message.get("requested_time"),
                "reason": message.get("reason"),
                "status": "pending",
                "created_at": datetime.utcnow().isoformat(),
                "raw_request": message,
            }
        )

        # Acknowledge message
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        logger_service.error(f"Error processing appointment request: {e}")
        # Negative acknowledgment with requeue=True to retry later
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def handle_report_notification(ch, method, properties, body):
    """Handle incoming report notifications"""
    try:
        # Parse message
        message = json.loads(body)
        logger_service.info(f"Received report notification: {message}")

        # Store in database
        mongodb_client = MongoDBClient(Config)
        mongodb_client.db.report_notifications.insert_one(
            {
                "report_id": message.get("report_id"),
                "patient_id": message.get("patient_id"),
                "doctor_id": message.get("doctor_id"),
                "status": message.get("status"),
                "received_at": datetime.utcnow().isoformat(),
                "raw_notification": message,
            }
        )

        # Acknowledge message
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        logger_service.error(f"Error processing report notification: {e}")
        # Negative acknowledgment with requeue=True to retry later
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def handle_radiology_report_completed(ch, method, properties, body):
    """Handle notifications about completed radiology reports"""
    try:
        # Parse message
        message = json.loads(body)
        logger_service.info(
            f"Received radiology report completed notification: {message}"
        )

        # Store in database
        mongodb_client = MongoDBClient(Config)
        mongodb_client.db.radiology_reports.insert_one(
            {
                "request_id": message.get("request_id"),
                "report_id": message.get("report_id"),
                "patient_id": message.get("patient_id"),
                "doctor_id": message.get("doctor_id"),
                "exam_type": message.get("exam_type"),
                "status": message.get("status"),
                "received_at": datetime.utcnow().isoformat(),
                "raw_notification": message,
            }
        )

        # Acknowledge message
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        logger_service.error(f"Error processing radiology report: {e}")
        # Negative acknowledgment with requeue=True to retry later
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def handle_prescription_notification(ch, method, properties, body):
    """Handle notifications about prescriptions"""
    try:
        # Parse message
        message = json.loads(body)
        logger_service.info(f"Received prescription notification: {message}")

        # Store in database
        mongodb_client = MongoDBClient(Config)
        mongodb_client.db.prescription_notifications.insert_one(
            {
                "prescription_id": message.get("prescription_id"),
                "patient_id": message.get("patient_id", "unknown"),
                "doctor_id": message.get("doctor_id", "unknown"),
                "action": message.get("action", "unknown"),
                "received_at": datetime.utcnow().isoformat(),
                "raw_notification": message,
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

        # Appointment requests
        rabbitmq_client.consume_messages(
            "appointment.requests", handle_appointment_request
        )

        # Report notifications
        rabbitmq_client.consume_messages(
            "doctor.notifications", handle_report_notification
        )

        # Radiology report completions
        rabbitmq_client.consume_messages(
            "doctor.radiology.reports", handle_radiology_report_completed
        )

        # Prescription events
        rabbitmq_client.consume_messages(
            "prescription.events", handle_prescription_notification
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
