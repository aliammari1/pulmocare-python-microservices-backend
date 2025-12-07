import json
from datetime import datetime

import pika

from config import Config
from services.logger_service import logger_service
from services.mongodb_client import MongoDBClient
from services.rabbitmq_client import RabbitMQClient


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


def handle_patient_data_request(ch, method, properties, body):
    """Handle requests for patient prescription data from patients service"""
    try:
        # Parse the request
        request = json.loads(body)
        patient_id = request.get("patient_id")
        reply_to = properties.reply_to
        correlation_id = properties.correlation_id

        logger_service.info(
            f"Received prescription data request for patient {patient_id}"
        )

        if not patient_id or not reply_to or not correlation_id:
            logger_service.error("Invalid request format: missing required fields")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # Get MongoDB connection
        mongodb_client_service = MongoDBClient(Config)
        mongodb_client = mongodb_client_service.client
        db = mongodb_client_service.db

        try:
            # Get prescriptions for this patient
            prescriptions = list(
                db.ordonnances.find({"patient_id": patient_id}).sort("created_at", -1)
            )

            # Format prescriptions for response
            formatted_prescriptions = []
            for prescription in prescriptions:
                formatted_prescriptions.append(
                    {
                        "id": str(prescription.get("_id")),
                        "doctor_id": prescription.get("doctor_id"),
                        "doctor_name": prescription.get(
                            "doctor_name", "Unknown Doctor"
                        ),
                        "created_at": (
                            prescription.get("created_at").isoformat()
                            if isinstance(prescription.get("created_at"), datetime)
                            else prescription.get("created_at")
                        ),
                        "status": prescription.get("status"),
                        "medications": prescription.get("medications", []),
                        "instructions": prescription.get("instructions", ""),
                        "last_updated": (
                            prescription.get("updated_at").isoformat()
                            if isinstance(prescription.get("updated_at"), datetime)
                            else prescription.get("updated_at", "")
                        ),
                    }
                )

            # Send the response
            rabbitmq_client = RabbitMQClient(Config)
            response = {
                "data": formatted_prescriptions,
                "count": len(formatted_prescriptions),
                "patient_id": patient_id,
                "timestamp": datetime.utcnow().isoformat(),
            }

            rabbitmq_client.channel.basic_publish(
                exchange="",  # Use default exchange for direct replies
                routing_key=reply_to,
                body=json.dumps(response),
                properties=pika.BasicProperties(
                    correlation_id=correlation_id, content_type="application/json"
                ),
            )

            logger_service.info(
                f"Sent {len(formatted_prescriptions)} prescriptions for patient {patient_id}"
            )
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            logger_service.error(f"Error retrieving prescriptions: {e}")
            # Send error response
            rabbitmq_client = RabbitMQClient(Config)
            error_response = {
                "error": f"Failed to retrieve prescriptions: {str(e)}",
                "data": [],
                "patient_id": patient_id,
                "timestamp": datetime.utcnow().isoformat(),
            }

            rabbitmq_client.channel.basic_publish(
                exchange="",
                routing_key=reply_to,
                body=json.dumps(error_response),
                properties=pika.BasicProperties(
                    correlation_id=correlation_id, content_type="application/json"
                ),
            )

            ch.basic_ack(delivery_tag=method.delivery_tag)

        finally:
            if mongodb_client:
                mongodb_client.close()
            if rabbitmq_client:
                rabbitmq_client.close()

    except Exception as e:
        logger_service.error(f"Error processing prescription data request: {str(e)}")
        ch.basic_ack(
            delivery_tag=method.delivery_tag
        )  # Acknowledge anyway to avoid requeuing


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

        # New consumer for patient data requests
        rabbitmq_client.channel.queue_declare(
            queue="patient.data.prescriptions", durable=True
        )

        rabbitmq_client.channel.queue_bind(
            exchange="medical.exchange",
            queue="patient.data.prescriptions",
            routing_key="patient.data.prescriptions.request",
        )

        rabbitmq_client.channel.basic_consume(
            queue="patient.data.prescriptions",
            on_message_callback=handle_patient_data_request,
        )

        logger_service.info("Started consuming messages")
        rabbitmq_client.channel.start_consuming()

    except Exception as e:
        logger_service.error(f"Consumer error: {str(e)}")
        if rabbitmq_client:
            rabbitmq_client.close()


if __name__ == "__main__":
    main()
