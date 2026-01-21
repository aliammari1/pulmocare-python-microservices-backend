import json
from datetime import datetime

from config import Config
from services.logger_service import logger_service
from services.rabbitmq_client import RabbitMQClient


def handle_medical_update(ch, method, properties, body):
    """Handle medical updates for patients"""
    try:
        # Parse message
        message = json.loads(body)
        logger_service.info(f"Received medical update: {message}")

        # Extract patient ID and update type from message
        patient_id = message.get("patient_id")
        update_type = method.routing_key.split(".")[-1]

        # Log that we've processed it
        logger_service.info(f"Processed {update_type} medical update for patient {patient_id}")

        # Here we'll just forward to a notification stream using RabbitMQ
        rabbitmq_client = RabbitMQClient(Config)
        rabbitmq_client.publish_patient_update(
            patient_id=patient_id,
            update_type="medical_update_processed",
            data={
                "original_update_type": update_type,
                "processed_at": datetime.utcnow().isoformat(),
                "status": "received",
            },
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

        # Extract key data
        appointment_id = message.get("appointment_id")
        patient_id = message.get("patient_id")
        doctor_id = message.get("doctor_id")
        status = message.get("status")

        # Log the appointment response
        logger_service.info(f"Appointment {appointment_id} for patient {patient_id} with doctor {doctor_id} status: {status}")

        # Forward the response as a notification to the patient
        rabbitmq_client = RabbitMQClient(Config)
        rabbitmq_client.send_notification(
            recipient_id=patient_id,
            recipient_type="patient",
            notification_type="appointment_update",
            message=f"Your appointment request has been {status}.",
            data={
                "appointment_id": appointment_id,
                "doctor_id": doctor_id,
                "status": status,
                "response_received_at": datetime.utcnow().isoformat(),
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

        # Extract key information
        prescription_id = message.get("prescription_id")
        patient_id = message.get("patient_id")
        action = message.get("action")

        # Log that we've processed the notification
        logger_service.info(f"Processed prescription {prescription_id} {action} notification for patient {patient_id}")

        # Send a patient notification via RabbitMQ
        rabbitmq_client = RabbitMQClient(Config)

        # Send a notification message to the patient
        notification_message = f"Your prescription has been {action}."
        if action == "created":
            notification_message = "A new prescription has been created for you."
        elif action == "filled":
            notification_message = "Your prescription is ready to be picked up."
        elif action == "dispensed":
            notification_message = "Your prescription has been dispensed."

        rabbitmq_client.send_notification(
            recipient_id=patient_id,
            recipient_type="patient",
            notification_type="prescription_update",
            message=notification_message,
            data={
                "prescription_id": prescription_id,
                "action": action,
                "notification_time": datetime.utcnow().isoformat(),
            },
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
        rabbitmq_client.consume_messages("patients.medical_updates", handle_medical_update)

        # Appointment responses
        rabbitmq_client.consume_messages("patients.appointments", handle_appointment_response)

        # Prescription notifications
        rabbitmq_client.consume_messages("patients.prescriptions", handle_prescription_notification)

        # Start consuming (this is a blocking call)
        logger_service.info("Starting to consume messages. Press CTRL+C to exit.")
        rabbitmq_client.channel.start_consuming()

    except KeyboardInterrupt:
        logger_service.info("Consumer stopped by user.")
    except Exception as e:
        logger_service.error(f"Consumer error: {e}")


if __name__ == "__main__":
    main()
