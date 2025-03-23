import json
import logging
from datetime import datetime
import pika
from pymongo import MongoClient
from config import Config
from services.rabbitmq_client import RabbitMQClient

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

def handle_validation_request(ch, method, properties, body):
    """Handle incoming prescription validation requests"""
    try:
        data = json.loads(body)
        prescription_id = data.get('prescription_id')
        doctor_id = data.get('doctor_id')
        
        logger.info(f"Received validation request for prescription {prescription_id}")
        
        # Get MongoDB connection
        mongodb_client, db = init_mongodb()
        if not mongodb_client:
            logger.error("Failed to connect to MongoDB")
            ch.basic_nack(delivery_tag=method.delivery_tag)
            return
            
        try:
            # Find the prescription
            prescription = db.prescriptions.find_one({'_id': prescription_id})
            if not prescription:
                logger.error(f"Prescription {prescription_id} not found")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return
            
            # Check doctor authorization
            if prescription.get('doctor_id') != doctor_id:
                logger.error(f"Doctor {doctor_id} not authorized to validate prescription {prescription_id}")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return
            
            # Update prescription status
            db.prescriptions.update_one(
                {'_id': prescription_id},
                {
                    '$set': {
                        'status': 'validated',
                        'validated_at': datetime.utcnow(),
                        'validated_by': doctor_id
                    }
                }
            )
            
            # Notify about validation
            rabbitmq_client = RabbitMQClient(Config)
            rabbitmq_client.publish_message(
                'medical.prescriptions',
                'prescription.validated',
                {
                    'event': 'prescription_validated',
                    'prescription_id': prescription_id,
                    'doctor_id': doctor_id,
                    'timestamp': datetime.utcnow().isoformat()
                }
            )
            
            logger.info(f"Successfully validated prescription {prescription_id}")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
        except Exception as e:
            logger.error(f"Error processing validation request: {str(e)}")
            ch.basic_nack(delivery_tag=method.delivery_tag)
            
        finally:
            if mongodb_client:
                mongodb_client.close()
            if rabbitmq_client:
                rabbitmq_client.close()
                
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        ch.basic_nack(delivery_tag=method.delivery_tag)

def handle_notification(ch, method, properties, body):
    """Handle incoming prescription notifications"""
    try:
        data = json.loads(body)
        prescription_id = data.get('prescription_id')
        event = data.get('event')
        
        logger.info(f"Received prescription notification: {event} for prescription {prescription_id}")
        
        # Get MongoDB connection
        mongodb_client, db = init_mongodb()
        if not mongodb_client:
            logger.error("Failed to connect to MongoDB")
            ch.basic_nack(delivery_tag=method.delivery_tag)
            return
            
        try:
            # Store notification
            notification = {
                'type': 'prescription',
                'prescription_id': prescription_id,
                'event': event,
                'data': data,
                'created_at': datetime.utcnow(),
                'read': False
            }
            
            db.prescription_notifications.insert_one(notification)
            logger.info(f"Stored notification for prescription {prescription_id}")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
        except Exception as e:
            logger.error(f"Error processing notification: {str(e)}")
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
            queue='prescription.validations',
            on_message_callback=handle_validation_request
        )
        
        rabbitmq_client.channel.basic_consume(
            queue='prescription.notifications',
            on_message_callback=handle_notification
        )
        
        logger.info("Started consuming messages")
        rabbitmq_client.channel.start_consuming()
        
    except Exception as e:
        logger.error(f"Consumer error: {str(e)}")
        if rabbitmq_client:
            rabbitmq_client.close()

if __name__ == '__main__':
    main()