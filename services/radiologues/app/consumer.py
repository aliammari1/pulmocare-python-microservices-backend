import json
from datetime import datetime

from services.logger_service import logger_service
from services.mongodb_client import MongoDBClient
from services.rabbitmq_client import RabbitMQClient

from config import Config


def handle_examination_request(ch, method, properties, body):
    """Handle incoming radiology examination requests"""
    try:
        # Parse message
        message = json.loads(body)
        logger_service.info(f"Received examination request: {message}")

        # Store in database
        mongodb_client = MongoDBClient(Config)
        mongodb_client.db.examination_requests.insert_one(
            {
                "request_id": message.get("request_id"),
                "doctor_id": message.get("doctor_id"),
                "patient_id": message.get("patient_id"),
                "patient_name": message.get("patient_name"),
                "exam_type": message.get("exam_type"),
                "reason": message.get("reason"),
                "urgency": message.get("urgency", "normal"),
                "status": "requested",
                "timestamp": datetime.utcnow().isoformat(),
                "raw_request": message,
            }
        )

        # Acknowledge message
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

        # Store in database
        mongodb_client = MongoDBClient(Config)
        mongodb_client.db.analysis_requests.insert_one(
            {
                "report_id": report_id,
                "received_at": datetime.utcnow().isoformat(),
                "status": "received",
                "report_data": report_data,
                "raw_request": message,
            }
        )

        # Here you would typically trigger the analysis process
        # For now, just acknowledge the message
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

        # Store in database
        mongodb_client = MongoDBClient(Config)
        mongodb_client.db.notifications.insert_one(
            {
                "notification_type": method.routing_key,
                "received_at": datetime.utcnow().isoformat(),
                "raw_notification": message,
            }
        )

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
        rabbitmq_client.consume_messages(
            "radiologues.examinations", handle_examination_request
        )

        # Report analysis requests
        rabbitmq_client.consume_messages(
            "radiologues.analysis", handle_report_analysis_request
        )

        # General notifications
        rabbitmq_client.consume_messages(
            "radiologues.notifications", handle_notification
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
