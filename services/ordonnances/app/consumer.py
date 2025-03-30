import json
from datetime import datetime

from services.logger_service import logger_service
from services.mongodb_client import MongoDBClient
from services.rabbitmq_client import RabbitMQClient

from config import Config


def handle_validation_request(ch, method, properties, body):
    """Handle incoming prescription validation requests"""
    try:
        data = json.loads(body)
        prescription_id = data.get("prescription_id")
        doctor_id = data.get("doctor_id")

        logger_service.info(
            f"Received validation request for prescription {prescription_id}"
        )

        # Get MongoDB connection
        mongodb_client_service = MongoDBClient(Config)
        mongodb_client = mongodb_client_service.client
        db = mongodb_client_service.db
        if not mongodb_client:
            logger_service.error("Failed to connect to MongoDB")
            ch.basic_nack(delivery_tag=method.delivery_tag)
            return

        try:
            # Find the prescription
            prescription = db.prescriptions.find_one({"_id": prescription_id})
            if not prescription:
                logger_service.error(f"Prescription {prescription_id} not found")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            # Check doctor authorization
            if prescription.get("doctor_id") != doctor_id:
                logger_service.error(
                    f"Doctor {doctor_id} not authorized to validate prescription {prescription_id}"
                )
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            # Update prescription status
            db.prescriptions.update_one(
                {"_id": prescription_id},
                {
                    "$set": {
                        "status": "validated",
                        "validated_at": datetime.utcnow(),
                        "validated_by": doctor_id,
                    }
                },
            )

            # Notify about validation
            rabbitmq_client = RabbitMQClient(Config)
            rabbitmq_client.publish_message(
                "medical.prescriptions",
                "prescription.validated",
                {
                    "event": "prescription_validated",
                    "prescription_id": prescription_id,
                    "doctor_id": doctor_id,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

            logger_service.info(
                f"Successfully validated prescription {prescription_id}"
            )
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            logger_service.error(f"Error processing validation request: {str(e)}")
            ch.basic_nack(delivery_tag=method.delivery_tag)

        finally:
            if mongodb_client:
                mongodb_client.close()
            if rabbitmq_client:
                rabbitmq_client.close()

    except Exception as e:
        logger_service.error(f"Error processing message: {str(e)}")
        ch.basic_nack(delivery_tag=method.delivery_tag)


def handle_notification(ch, method, properties, body):
    """Handle incoming prescription notifications"""
    try:
        data = json.loads(body)
        prescription_id = data.get("prescription_id")
        event = data.get("event")

        logger_service.info(
            f"Received prescription notification: {event} for prescription {prescription_id}"
        )

        # Get MongoDB connection
        mongodb_client_service = MongoDBClient(Config)
        mongodb_client = mongodb_client_service.client
        db = mongodb_client_service.db
        if not mongodb_client:
            logger_service.error("Failed to connect to MongoDB")
            ch.basic_nack(delivery_tag=method.delivery_tag)
            return

        try:
            # Store notification
            notification = {
                "type": "prescription",
                "prescription_id": prescription_id,
                "event": event,
                "data": data,
                "created_at": datetime.utcnow(),
                "read": False,
            }

            db.prescription_notifications.insert_one(notification)
            logger_service.info(
                f"Stored notification for prescription {prescription_id}"
            )
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            logger_service.error(f"Error processing notification: {str(e)}")
            ch.basic_nack(delivery_tag=method.delivery_tag)

        finally:
            if mongodb_client:
                mongodb_client.close()

    except Exception as e:
        logger_service.error(f"Error processing message: {str(e)}")
        ch.basic_nack(delivery_tag=method.delivery_tag)


def main():
    """Main consumer function"""
    try:
        # Create RabbitMQ client
        rabbitmq_client = RabbitMQClient(Config)

        # Setup consumers
        rabbitmq_client.channel.basic_consume(
            queue="prescription.validations",
            on_message_callback=handle_validation_request,
        )

        rabbitmq_client.channel.basic_consume(
            queue="prescription.notifications", on_message_callback=handle_notification
        )

        logger_service.info("Started consuming messages")
        rabbitmq_client.channel.start_consuming()

    except Exception as e:
        logger_service.error(f"Consumer error: {str(e)}")
        if rabbitmq_client:
            rabbitmq_client.close()


if __name__ == "__main__":
    main()
