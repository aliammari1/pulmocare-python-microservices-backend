import json
from datetime import datetime

from services.logger_service import logger_service
from services.mongodb_client import MongoDBClient
from services.rabbitmq_client import RabbitMQClient
from services.report_service import ReportService

from config import Config


def handle_report_analysis_result(ch, method, properties, body):
    """Handle analysis results for reports"""
    try:
        # Parse message
        message = json.loads(body)
        logger_service.info(f"Received report analysis result: {message}")

        # Store in database
        mongodb_client = MongoDBClient(Config)
        report_id = message.get("report_id")

        # Update the report analysis status
        mongodb_client.db.report_analyses.update_one(
            {"report_id": report_id},
            {
                "$set": {
                    "status": "completed",
                    "completed_at": datetime.utcnow().isoformat(),
                    "analysis_data": message.get("analysis_data", {}),
                    "findings": message.get("findings", []),
                    "summary": message.get("summary", ""),
                }
            },
        )

        # Also update the report status
        mongodb_client.db.reports.update_one(
            {"report_id": report_id},
            {
                "$set": {
                    "analysis_status": "completed",
                    "analyzed_at": datetime.utcnow().isoformat(),
                }
            },
        )

        # Acknowledge message
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        logger_service.error(f"Error processing report analysis result: {e}")
        # Negative acknowledgment with requeue=True to retry later
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def handle_summary_result(ch, method, properties, body):
    """Handle summary generation results"""
    try:
        # Parse message
        message = json.loads(body)
        logger_service.info(f"Received summary result: {message}")

        # Store in database
        mongodb_client = MongoDBClient(Config)
        job_id = message.get("job_id")

        # Update the summary job
        mongodb_client.db.summary_jobs.update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "status": "completed",
                    "completed_at": datetime.utcnow().isoformat(),
                    "summary": message.get("summary", ""),
                    "metadata": message.get("metadata", {}),
                }
            },
        )

        # Acknowledge message
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        logger_service.error(f"Error processing summary result: {e}")
        # Negative acknowledgment with requeue=True to retry later
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def handle_new_report(ch, method, properties, body):
    """Handle new report notifications"""
    try:
        # Parse message
        message = json.loads(body)
        logger_service.info(f"Received new report notification: {message}")

        # Store in database
        mongodb_client = MongoDBClient(Config)
        rabbitmq_client = RabbitMQClient(Config)
        report_service = ReportService(mongodb_client, None, rabbitmq_client)

        report_id = message.get("report_id")

        # Check if report already exists
        existing = mongodb_client.db.reports.find_one({"report_id": report_id})
        if not existing:
            # Create new report record
            mongodb_client.db.reports.insert_one(
                {
                    "report_id": report_id,
                    "doctor_id": message.get("doctor_id"),
                    "patient_id": message.get("patient_id"),
                    "exam_type": message.get("exam_type", "unknown"),
                    "created_at": datetime.utcnow().isoformat(),
                    "status": "received",
                    "analysis_status": "pending",
                    "source": "external",
                    "raw_data": message,
                }
            )

            # Automatically queue for analysis if configured to do so
            if Config.AUTO_ANALYZE_REPORTS:
                report_service.queue_report_for_analysis(report_id)

        # Acknowledge message
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        logger_service.error(f"Error processing new report: {e}")
        # Negative acknowledgment with requeue=True to retry later
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def main():
    """Main consumer function"""
    try:
        # Initialize clients
        rabbitmq_client = RabbitMQClient(Config)

        # Set up consumers for different queues

        # Report analysis results
        rabbitmq_client.consume_messages(
            "reports.analysis.results", handle_report_analysis_result
        )

        # Summary generation results
        rabbitmq_client.consume_messages(
            "reports.summary.results", handle_summary_result
        )

        # New report notifications
        rabbitmq_client.consume_messages("reports.new", handle_new_report)

        # Start consuming (this is a blocking call)
        logger_service.info("Starting to consume messages. Press CTRL+C to exit.")
        rabbitmq_client.channel.start_consuming()

    except KeyboardInterrupt:
        logger_service.info("Consumer stopped by user.")
    except Exception as e:
        logger_service.error(f"Consumer error: {e}")


if __name__ == "__main__":
    main()
