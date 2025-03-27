import json
import logging
from datetime import datetime

import pika
from pymongo import MongoClient
from services.rabbitmq_client import RabbitMQClient

from config import Config

# Set up logging
logging.config.dictConfig(Config.init_logging())
logger = logging.getLogger(__name__)


def init_mongodb():
    """Initialize MongoDB connection"""
    try:
        client = MongoClient(Config.get_mongodb_uri())
        db = client[Config.MONGODB_DATABASE]
        return client, db
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {str(e)}")
        return None, None


def handle_appointment_request(ch, method, properties, body):
    """Handle incoming appointment requests"""
    try:
        data = json.loads(body)
        appointment_id = data.get("appointment_id")
        doctor_id = data.get("doctor_id")
        patient_id = data.get("patient_id")
        requested_time = data.get("requested_time")

        logger.info(f"Received appointment request for doctor {doctor_id}")

        # Get MongoDB connection
        mongodb_client, db = init_mongodb()
        if not mongodb_client:
            logger.error("Failed to connect to MongoDB")
            ch.basic_nack(delivery_tag=method.delivery_tag)
            return

        try:
            # Check doctor availability
            doctor = db.doctors.find_one({"_id": doctor_id})
            if not doctor:
                logger.error(f"Doctor {doctor_id} not found")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            # Store appointment request
            db.appointments.insert_one(
                {
                    "_id": appointment_id,
                    "doctor_id": doctor_id,
                    "patient_id": patient_id,
                    "requested_time": requested_time,
                    "status": "pending",
                    "created_at": datetime.utcnow(),
                }
            )

            # Notify doctor about new appointment
            rabbitmq_client = RabbitMQClient(Config)
            rabbitmq_client.publish_message(
                "medical.events",
                "doctor.appointment.requested",
                {
                    "event": "appointment_requested",
                    "appointment_id": appointment_id,
                    "doctor_id": doctor_id,
                    "patient_id": patient_id,
                    "requested_time": requested_time,
                },
            )

            logger.info(f"Successfully processed appointment request {appointment_id}")
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            logger.error(f"Error processing appointment request: {str(e)}")
            ch.basic_nack(delivery_tag=method.delivery_tag)

        finally:
            if mongodb_client:
                mongodb_client.close()
            if rabbitmq_client:
                rabbitmq_client.close()

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        ch.basic_nack(delivery_tag=method.delivery_tag)


def handle_report_notification(ch, method, properties, body):
    """Handle incoming report notifications"""
    try:
        data = json.loads(body)
        report_id = data.get("report_id")
        event = data.get("event")

        logger.info(f"Received report notification: {event} for report {report_id}")

        # Get MongoDB connection
        mongodb_client, db = init_mongodb()
        if not mongodb_client:
            logger.error("Failed to connect to MongoDB")
            ch.basic_nack(delivery_tag=method.delivery_tag)
            return

        try:
            # Update doctor's notification collection
            notification = {
                "type": "report",
                "report_id": report_id,
                "event": event,
                "created_at": datetime.utcnow(),
                "read": False,
            }

            db.doctor_notifications.insert_one(notification)
            logger.info(f"Stored notification for report {report_id}")
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            logger.error(f"Error processing report notification: {str(e)}")
            ch.basic_nack(delivery_tag=method.delivery_tag)

        finally:
            if mongodb_client:
                mongodb_client.close()

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        ch.basic_nack(delivery_tag=method.delivery_tag)


def main():
    """Main consumer function"""
    try:
        # Create RabbitMQ client
        rabbitmq_client = RabbitMQClient(Config)

        # Setup consumers
        rabbitmq_client.channel.basic_consume(
            queue="appointment.requests", on_message_callback=handle_appointment_request
        )

        rabbitmq_client.channel.basic_consume(
            queue="doctor.notifications", on_message_callback=handle_report_notification
        )

        logger.info("Started consuming messages")
        rabbitmq_client.channel.start_consuming()

    except Exception as e:
        logger.error(f"Consumer error: {str(e)}")
        if rabbitmq_client:
            rabbitmq_client.close()


if __name__ == "__main__":
    main()
