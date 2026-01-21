import json

from config import Config
from services.logger_service import logger_service
from services.rabbitmq_client import RabbitMQClient


def handle_examination_request(ch, method, properties, body):
    """Handle incoming radiology examination requests"""
    try:
        # Parse message
        message = json.loads(body)
        logger_service.info(f"Received examination request: {message}")

        # Extract relevant info for logging/processing
        request_id = message.get("request_id")
        doctor_id = message.get("doctor_id")
        patient_id = message.get("patient_id")

        # Log the request details
        logger_service.info(f"Processing examination request {request_id} for patient {patient_id} from doctor {doctor_id}")

        # Process the examination request
        # In a real scenario, you might need to handle this data differently
        # For now, we'll just acknowledge receipt and prepare a sample response

        # Initialize RabbitMQ client to send notifications or responses
        rabbitmq_client = RabbitMQClient(Config)

        # Notify the doctor that we received the request
        rabbitmq_client.send_notification(
            recipient_id=doctor_id,
            recipient_type="doctor",
            notification_type="examination_received",
            message=f"Radiology examination request {request_id} has been received and is being processed.",
            data={"request_id": request_id, "status": "received"},
        )

        # Acknowledge the message
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        logger_service.error(f"Error processing examination request: {e}")
        # Negative acknowledgment with requeue=True to retry later
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def handle_report_analysis_request(ch, method, properties, body):
    """Handle requests for radiology report analysis"""
    try:
        # Parse message
        message = json.loads(body)
        logger_service.info(f"Received report analysis request: {message}")

        # Get the report data
        report_id = message.get("report_id")
        report_data = message.get("report_data")

        # Log the analysis request
        logger_service.info(f"Processing report analysis request for report {report_id}")

        # In a real scenario, you would process the report data here
        # For now, we'll simulate receiving and processing

        # Initialize RabbitMQ client for response
        rabbitmq_client = RabbitMQClient(Config)

        # Publish a status update about the report analysis
        rabbitmq_client.update_radiology_report_status(
            report_id=report_id,
            status="analysis_started",
            updated_by="radiologues-service",
        )

        # Acknowledge the message
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        logger_service.error(f"Error processing report analysis request: {e}")
        # Negative acknowledgment with requeue=True to retry later
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def handle_notification(ch, method, properties, body):
    """Handle general notifications for radiologists"""
    try:
        # Parse message
        message = json.loads(body)
        logger_service.info(f"Received notification: {message}")

        # Process notification based on routing key
        notification_type = method.routing_key
        logger_service.info(f"Processing notification type: {notification_type}")

        # Here you could dispatch to different handlers based on notification type
        # For now just acknowledge the message

        # Acknowledge message
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        logger_service.error(f"Error processing notification: {e}")
        # Negative acknowledgment with requeue=True to retry later
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def main():
    """Main consumer function"""
    try:
        # Initialize clients
        rabbitmq_client = RabbitMQClient(Config)

        # Set up consumers for different queues

        # Examination requests
        rabbitmq_client.consume_messages("radiologues.examinations", handle_examination_request)

        # Report analysis requests
        rabbitmq_client.consume_messages("radiologues.analysis", handle_report_analysis_request)

        # General notifications
        rabbitmq_client.consume_messages("radiologues.notifications", handle_notification)

        # Start consuming (this is a blocking call)
        logger_service.info("Starting to consume messages. Press CTRL+C to exit.")
        rabbitmq_client.channel.start_consuming()

    except KeyboardInterrupt:
        logger_service.info("Consumer stopped by user.")
    except Exception as e:
        logger_service.error(f"Consumer error: {e}")


if __name__ == "__main__":
    main()
