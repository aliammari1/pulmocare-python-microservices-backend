import json
from datetime import datetime

from services.logger_service import logger_service
from services.mongodb_client import MongoDBClient
from services.rabbitmq_client import RabbitMQClient

from config import Config


def handle_analysis_request(ch, method, properties, body):
    """Handle incoming radiology analysis requests"""
    try:
        data = json.loads(body)
        report_id = data.get("report_id")
        image_data = data.get("image_data")

        logger_service.info(f"Received analysis request for report {report_id}")

        # Get MongoDB connection
        mongodb_client_service = MongoDBClient(Config)
        mongodb_client = mongodb_client_service.client
        db = mongodb_client_service.db
        if not mongodb_client:
            logger_service.error("Failed to connect to MongoDB")
            ch.basic_nack(delivery_tag=method.delivery_tag)
            return

        try:
            # Find the radiology report
            report = db.radiology_reports.find_one({"_id": report_id})
            if not report:
                logger_service.error(f"Report {report_id} not found")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            # Perform image analysis
            analysis_result = (
                "the analyis result modify it in the radilogues service consumer.py"
            )

            # Update report with analysis results
            db.radiology_reports.update_one(
                {"_id": report_id},
                {
                    "$set": {
                        "analysis": analysis_result,
                        "analyzed_at": datetime.utcnow(),
                        "status": "analyzed",
                    }
                },
            )

            # Publish analysis results
            rabbitmq_client = RabbitMQClient(Config)
            rabbitmq_client.publish_analysis_result(report_id, analysis_result)

            logger_service.info(f"Successfully analyzed report {report_id}")
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            logger_service.error(f"Error processing analysis request: {str(e)}")
            ch.basic_nack(delivery_tag=method.delivery_tag)

        finally:
            if mongodb_client:
                mongodb_client.close()
            if rabbitmq_client:
                rabbitmq_client.close()

    except Exception as e:
        logger_service.error(f"Error processing message: {str(e)}")
        ch.basic_nack(delivery_tag=method.delivery_tag)


def main():
    """Main consumer function"""
    try:
        # Create RabbitMQ client
        rabbitmq_client = RabbitMQClient(Config)

        # Setup analysis request consumer
        rabbitmq_client.channel.basic_consume(
            queue="radiology.analysis", on_message_callback=handle_analysis_request
        )

        logger_service.info("Started consuming analysis requests")
        rabbitmq_client.channel.start_consuming()

    except Exception as e:
        logger_service.error(f"Consumer error: {str(e)}")
        if rabbitmq_client:
            rabbitmq_client.close()


if __name__ == "__main__":
    main()
