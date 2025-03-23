from flask import Flask, jsonify, request, make_response
from flask_cors import CORS
from pymongo import MongoClient
import os
import random
import smtplib
from email.mime.text import MIMEText
import jwt
from functools import wraps
from datetime import datetime, timedelta
import logging
from dotenv import load_dotenv
from bson import ObjectId
import inspect
from models.patient import Patient
from consul_service import ConsulService
from config import Config
import sys
from decorator.health_check import health_check_middleware

print("Patient class parameters:", inspect.signature(Patient.__init__))
print("Patient class source:", inspect.getsource(Patient.__init__))
print("Current directory:", os.getcwd())
print("List of files in models:", os.listdir("models"))

load_dotenv()

app = Flask(__name__)
CORS(app)

# Apply health check middleware
app = health_check_middleware(Config)(app)

print("Patient class: ", Patient)
# MongoDB configuration
client = MongoClient('mongodb://admin:admin@localhost:27017/')  # Adjust if using a different host/port
db = client["medapp"]  # Use your database name
patients_collection = db["patients"]

print("MongoDB Connection Successful")

JWT_SECRET = os.getenv('JWT_SECRET', 'replace-with-strong-secret')

logging.basicConfig(level=logging.WARNING)  # Change DEBUG to WARNING
logger = logging.getLogger(__name__)

# Optional: Specifically silence PyMongo's debug logs
logging.getLogger('pymongo').setLevel(logging.WARNING)

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'error': 'Token missing'}), 401
        token = auth_header.split()[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            user_id = payload['user_id']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        return f(user_id, *args, **kwargs)
    return decorated

def send_otp_email(to_email, otp):
    try:
        sender_email = os.getenv('EMAIL_ADDRESS')
        sender_password = os.getenv('EMAIL_PASSWORD')
        
        logger.warning(f"Email config - Address: {sender_email}, Password length: {len(sender_password) if sender_password else 0}")
        
        if not sender_email or not sender_password:
            logger.error("Email configuration missing in .env file")
            return False
            
        msg = MIMEText(f"Your OTP code for password reset is: {otp}\nThis code will expire in 15 minutes.")
        msg['Subject'] = 'Medicare - Password Reset OTP'
        msg['From'] = sender_email
        msg['To'] = to_email

        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                smtp.login(sender_email, sender_password)
                smtp.send_message(msg)
                logger.warning(f"OTP email sent successfully to {to_email}")
                return True
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"Gmail authentication failed: {str(e)}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending email: {str(e)}")
        return False

@app.route('/api/patient/signup', methods=['POST'])
def patient_signup():
    try:
        data = request.get_json()
        print(f"Received data: {data}")

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        required_fields = ['name', 'email', 'password']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({'error': f'Missing required fields: {", ".join(missing_fields)}'}), 400

        if patients_collection.find_one({'email': data['email']}):
            return jsonify({'error': 'Email already registered'}), 400

        patient_id = str(ObjectId())
        
        # Create patient with correct parameters
        patient = Patient(
            id=patient_id,
            name=data['name'],
            email=data['email'],
            phoneNumber=data.get('phoneNumber'),
            password=data['password']  # This will be hashed by the constructor
        )

        # Convert to dict and insert
        patient_dict = patient.to_dict()
        result = patients_collection.insert_one(patient_dict)

        # Prepare response
        response_data = patient_dict.copy()
        del response_data['password_hash']
        response_data['_id'] = str(result.inserted_id)

        return jsonify(response_data), 201

    except Exception as e:
        logger.error(f"Error in patient_signup: {str(e)}")
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500

@app.route('/api/patient/login', methods=['POST'])
def patient_login():
    from werkzeug.security import check_password_hash
    
    data = request.get_json()
    patient_data = patients_collection.find_one({'email': data['email']})
    
    if not patient_data:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # Use check_password_hash directly since your Patient class doesn't have this method
    if check_password_hash(patient_data['password_hash'], data['password']):
        token = jwt.encode(
            {'user_id': str(patient_data['_id']), 'exp': datetime.utcnow() + timedelta(days=1)}, 
            JWT_SECRET, 
            algorithm='HS256'
        )
        return jsonify({
            'token': token, 
            'id': str(patient_data['_id']), 
            'name': patient_data['name'], 
            'email': patient_data['email']
        }), 200
    
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/api/patient/forgot-password', methods=['POST'])
def patient_forgot_password():
    try:
        data = request.get_json()
        email = data.get('email')

        logger.debug(f"Forgot password request received for email: {email}")
        
        if not email:
            return jsonify({'error': 'Email is required'}), 400
            
        patient_data = patients_collection.find_one({'email': email})
        if not patient_data:
            logger.debug(f"Email not found: {email}")
            return jsonify({'error': 'Email not found'}), 404
            
        otp = str(random.randint(100000, 999999))
        logger.debug(f"Generated OTP: {otp}")
        if send_otp_email(email, otp):
            patients_collection.update_one(
                {'email': email}, 
                {
                    '$set': {
                        'reset_otp': otp,
                        'otp_expiry': datetime.utcnow() + timedelta(minutes=15)
                    }
                }
            )
            logger.debug("OTP sent and saved successfully")
            return jsonify({'message': 'OTP sent successfully'}), 200
        else:
            logger.error("Failed to send OTP email")
            return jsonify({'error': 'Failed to send OTP email'}), 500
            
    except Exception as e:
        logger.error(f"Error in forgot_password: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/patient/verify-otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    email, otp = data.get('email'), data.get('otp')
    result = patients_collection.find_one({'email': email, 'reset_otp': otp, 'otp_expiry': {'$gt': datetime.utcnow()}})
    if not result:
        return jsonify({'error': 'Invalid or expired OTP'}), 400
    return jsonify({'message': 'OTP verified successfully'}), 200

@app.route('/api/patient/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json()
    email, otp, new_password = data.get('email'), data.get('otp'), data.get('newPassword')
    patient_data = patients_collection.find_one({'email': email, 'reset_otp': otp, 'otp_expiry': {'$gt': datetime.utcnow()}})
    if not patient_data:
        return jsonify({'error': 'Invalid or expired OTP'}), 400
    patient = Patient.from_dict(patient_data)
    patient.set_password(new_password)  # Ensure password is hashed here
    patients_collection.update_one({'email': email}, {'$set': {'password_hash': patient.password_hash}, '$unset': {'reset_otp': '', 'otp_expiry': ''}})
    return jsonify({'message': 'Password reset successful'}), 200

@app.route('/api/test-email-config', methods=['GET'])
def test_email_config():
    sender_email = os.getenv('EMAIL_ADDRESS')
    sender_password = os.getenv('EMAIL_PASSWORD')
    
    config_info = {
        'email_configured': bool(sender_email and sender_password),
        'email_address': sender_email,
        'password_length': len(sender_password) if sender_password else 0
    }
    
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(sender_email, sender_password)
            config_info['smtp_login'] = 'successful'
    except Exception as e:
        config_info['smtp_login'] = 'failed'
        config_info['error'] = str(e)
    
    return jsonify(config_info)

@app.route('/health')
def health():
    """Health check endpoint"""
    try:
        # Test MongoDB connection
        client.admin.command('ping')
        return jsonify({
            'status': 'UP',
            'timestamp': datetime.now().isoformat(),
            'service': 'patients',
            'database': 'connected'
        })
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            'status': 'DOWN',
            'error': str(e),
            'service': 'patients'
        }), 503

@app.route('/api/patient/list', methods=['GET'])
def get_all_patients():
    try:
        # Get all patients from MongoDB
        patients_list = list(patients_collection.find({}, {'password_hash': 0, 'reset_otp': 0, 'otp_expiry': 0}))
        
        # Convert ObjectId to string for JSON serialization
        for patient in patients_list:
            patient['_id'] = str(patient['_id'])
        
        return jsonify(patients_list), 200
    except Exception as e:
        logger.error(f"Error getting patients list: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Register with Consul
    try:
        consul_service = ConsulService(Config)
        consul_service.register_service()
        logger.info(f"Registered {Config.SERVICE_NAME} with Consul")
    except Exception as e:
        logger.error(f"Failed to register with Consul: {e}")
        
    app.run(host=Config.HOST, port=Config.PORT, debug=True)