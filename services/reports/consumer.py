import json
import logging
from datetime import datetime
import pika
from pymongo import MongoClient
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

def callback(ch, method, properties, body):
    """Process incoming messages"""
    try:
        data = json.loads(body)
        report_id = data.get('report_id')
        logger.info(f"Received analysis request for report {report_id}")
        
        # Get MongoDB connection
        mongodb_client, db = init_mongodb()
        if not mongodb_client:
            logger.error("Failed to connect to MongoDB")
            ch.basic_nack(delivery_tag=method.delivery_tag)
            return
            
        # Get report from database
        report = db.reports.find_one({'_id': report_id})
        if not report:
            logger.error(f"Report {report_id} not found")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return
            
        # Analyze report
        # analysis_result = analyze_report(report)
        analysis_result = ""
        # Update report with analysis
        db.reports.update_one(
            {'_id': report_id},
            {
                '$set': {
                    'analysis': analysis_result,
                    'analyzed_at': datetime.utcnow()
                }
            }
        )
        
        logger.info(f"Successfully analyzed report {report_id}")
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        ch.basic_nack(delivery_tag=method.delivery_tag)
    finally:
        if mongodb_client:
            mongodb_client.close()

def main():
    """Main consumer function"""
    try:
        # Connect to RabbitMQ
        credentials = pika.PlainCredentials(
            Config.RABBITMQ_USER,
            Config.RABBITMQ_PASS
        )
        
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=Config.RABBITMQ_HOST,
                port=Config.RABBITMQ_PORT,
                virtual_host=Config.RABBITMQ_VHOST,
                credentials=credentials,
                heartbeat=600
            )
        )
        
        channel = connection.channel()
        
        # Ensure queue exists
        channel.queue_declare(
            queue='report.analysis',
            durable=True
        )
        
        # Set QoS
        channel.basic_qos(prefetch_count=1)
        
        # Start consuming
        channel.basic_consume(
            queue='report.analysis',
            on_message_callback=callback
        )
        
        logger.info("Started consuming from report.analysis queue")
        channel.start_consuming()
        
    except Exception as e:
        logger.error(f"Consumer error: {str(e)}")
        if 'connection' in locals() and connection.is_open:
            connection.close()

if __name__ == '__main__':
    main()