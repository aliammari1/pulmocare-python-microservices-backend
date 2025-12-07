import json
from datetime import datetime

from config import Config
from services.logger_service import logger_service
from services.rabbitmq_client import RabbitMQClient
from services.redis_client import RedisClient


def handle_appointment_request(ch, method, properties, body):
    """Handle incoming appointment requests"""
    try:
        # Parse message
        message = json.loads(body)
        logger_service.info(f"Received appointment request: {message}")

        # Store in Redis
        redis_client = RedisClient(Config)
        appointment_id = message.get(
            "appointment_id", str(datetime.utcnow().timestamp())
        )

        # Structure the data
        appointment_data = {
            "appointment_id": appointment_id,
            "patient_id": message.get("patient_id"),
            "doctor_id": message.get("doctor_id"),
            "requested_time": message.get("requested_time"),
            "reason": message.get("reason"),
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "raw_request": json.dumps(message),
        }

        # Store in Redis with expiration of 30 days (2592000 seconds)
        redis_client.client.setex(
            f"appointment:{appointment_id}", 2592000, json.dumps(appointment_data)
        )

        # Add to doctor's appointment list
        doctor_id = message.get("doctor_id")
        if doctor_id:
            redis_client.client.sadd(f"doctor:{doctor_id}:appointments", appointment_id)

        # Add to patient's appointment list
        patient_id = message.get("patient_id")
        if patient_id:
            redis_client.client.sadd(
                f"patient:{patient_id}:appointments", appointment_id
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

        # Store in Redis
        redis_client = RedisClient(Config)
        report_id = message.get("report_id", str(datetime.utcnow().timestamp()))

        # Structure the data
        report_data = {
            "report_id": report_id,
            "patient_id": message.get("patient_id"),
            "doctor_id": message.get("doctor_id"),
            "status": message.get("status"),
            "received_at": datetime.utcnow().isoformat(),
            "raw_notification": json.dumps(message),
        }

        # Store in Redis with expiration of 30 days
        redis_client.client.setex(
            f"report_notification:{report_id}", 2592000, json.dumps(report_data)
        )

        # Add to doctor's report list
        doctor_id = message.get("doctor_id")
        if doctor_id:
            redis_client.client.sadd(f"doctor:{doctor_id}:reports", report_id)

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

        # Store in Redis
        redis_client = RedisClient(Config)
        report_id = message.get("report_id", str(datetime.utcnow().timestamp()))

        # Structure the data
        radiology_data = {
            "request_id": message.get("request_id"),
            "report_id": report_id,
            "patient_id": message.get("patient_id"),
            "doctor_id": message.get("doctor_id"),
            "exam_type": message.get("exam_type"),
            "status": message.get("status"),
            "received_at": datetime.utcnow().isoformat(),
            "raw_notification": json.dumps(message),
        }

        # Store in Redis with expiration of 30 days
        redis_client.client.set(
            f"radiology_report:{report_id}", json.dumps(radiology_data), ex=2592000
        )

        # Add to doctor's radiology reports list
        doctor_id = message.get("doctor_id")
        if doctor_id:
            redis_client.client.sadd(f"doctor:{doctor_id}:radiology_reports", report_id)

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

        # Store in Redis
        redis_client = RedisClient(Config)
        prescription_id = message.get(
            "prescription_id", str(datetime.utcnow().timestamp())
        )

        # Structure the data
        prescription_data = {
            "prescription_id": prescription_id,
            "patient_id": message.get("patient_id", "unknown"),
            "doctor_id": message.get("doctor_id", "unknown"),
            "action": message.get("action", "unknown"),
            "received_at": datetime.utcnow().isoformat(),
            "raw_notification": json.dumps(message),
        }

        # Store in Redis with expiration of 30 days
        redis_client.client.set(
            f"prescription_notification:{prescription_id}",
            json.dumps(prescription_data),
            ex=2592000,
        )

        # Add to doctor's prescription notifications list
        doctor_id = message.get("doctor_id")
        if doctor_id and doctor_id != "unknown":
            redis_client.client.sadd(
                f"doctor:{doctor_id}:prescriptions", prescription_id
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
