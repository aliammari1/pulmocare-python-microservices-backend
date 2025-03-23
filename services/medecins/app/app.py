from flask import Flask, jsonify, request, make_response
from flask_cors import CORS
from pymongo import MongoClient
from models.doctor import Doctor
import os
import socket
import logging
from bson import ObjectId
from dotenv import load_dotenv
import random
import smtplib
from email.mime.text import MIMEText
import jwt
from functools import wraps
from datetime import datetime, timedelta
import re
import base64
import io
from PIL import Image
import pytesseract
from services.consul_service import ConsulService
from config import Config
import sys
from decorator.health_check import health_check_middleware

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Apply health check middleware
app = health_check_middleware(Config)(app)

# MongoDB configuration
client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://admin:admin@localhost:27017/'))
db = client.medapp
doctors_collection = db.doctors

JWT_SECRET = os.getenv('JWT_SECRET', 'replace-with-strong-secret')

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
        except:
            return jsonify({'error': 'Invalid token'}), 401
        return f(user_id, *args, **kwargs)
    return decorated

def send_otp_email(to_email, otp):
    try:
        sender_email = os.getenv('EMAIL_ADDRESS')
        sender_password = os.getenv('EMAIL_PASSWORD')
        
        logger.debug(f"Email configuration - Sender: {sender_email}, Password length: {len(sender_password) if sender_password else 0}")
        
        if not sender_email or not sender_password:
            logger.error("Email configuration missing")
            raise Exception("Email configuration missing")

        msg = MIMEText(f'''
        Hello,

        Your OTP code for password reset is: {otp}

        This code will expire in 15 minutes.
        If you did not request this code, please ignore this email.

        Best regards,
        Medicare Team
        ''')
        
        msg['Subject'] = 'Medicare - Password Reset OTP'
        msg['From'] = sender_email
        msg['To'] = to_email

        try:
            logger.debug("Attempting SMTP connection to smtp.gmail.com:465")
            smtp = smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10)
            logger.debug("SMTP connection successful")
            
            logger.debug("Attempting SMTP login")
            smtp.login(sender_email, sender_password)
            logger.debug("SMTP login successful")
            
            logger.debug("Sending email")
            smtp.send_message(msg)
            logger.debug("Email sent successfully")
            
            smtp.quit()
            return True
            
        except smtplib.SMTPAuthenticationError as auth_error:
            logger.error(f"SMTP Authentication failed - Details: {str(auth_error)}")
            raise Exception(f"Email authentication failed. Please check your credentials.")
            
        except smtplib.SMTPException as smtp_error:
            logger.error(f"SMTP error occurred: {str(smtp_error)}")
            raise Exception(f"Email sending failed: {str(smtp_error)}")
            
        except Exception as e:
            logger.error(f"Unexpected SMTP error: {str(e)}")
            raise Exception(f"Unexpected error while sending email: {str(e)}")
            
    except Exception as e:
        logger.error(f"Email sending error: {str(e)}")
        return False

# Add health check endpoint for Consul
# @app.route('/health', methods=['GET'])
# def health_check():
#     """Health check endpoint for Consul"""
#     try:
#         # Ping the MongoDB to check connection
#         client.admin.command('ping')
        
#         return jsonify({
#             'status': 'UP',
#             'service': Config.SERVICE_NAME,
#             'timestamp': datetime.utcnow().isoformat(),
#             'dependencies': {
#                 'mongodb': 'UP'
#             }
#         }), 200
#     except Exception as e:
#         logger.error(f"Health check failed: {str(e)}")
#         return jsonify({
#             'status': 'DOWN',
#             'error': str(e),
#             'timestamp': datetime.utcnow().isoformat()
#         }), 503

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.get_json()
    
    if doctors_collection.find_one({'email': data['email']}):
        return jsonify({'error': 'Email already registered'}), 400

    doctor = Doctor(
        name=data['name'],
        email=data['email'],
        specialty=data['specialty'],
        phone_number=data['phoneNumber'],
        address=data['address'],
        password=data['password']
    )

    # Insert the doctor document with is_verified field
    result = doctors_collection.insert_one({
        '_id': doctor._id,
        'name': doctor.name,
        'email': doctor.email,
        'password_hash': doctor.password_hash,
        'specialty': doctor.specialty,
        'phone_number': doctor.phone_number,
        'address': doctor.address,
        'is_verified': False  # Add default verification status
    })

    return jsonify(doctor.to_dict()), 201

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        logger.debug(f"Login attempt for email: {data.get('email')}")  # Add debug log
        
        if not data or 'email' not in data or 'password' not in data:
            return jsonify({'error': 'Email and password are required'}), 400

        doctor_data = doctors_collection.find_one({'email': data['email']})
        if not doctor_data:
            logger.debug("Email not found")  # Add debug log
            return jsonify({'error': 'Invalid credentials'}), 401

        doctor = Doctor.from_dict(doctor_data)
        doctor.password_hash = doctor_data['password_hash']

        if doctor.check_password(data['password']):
            token = jwt.encode(
                {
                    'user_id': str(doctor_data['_id']),
                    'exp': datetime.utcnow() + timedelta(days=1)
                },
                JWT_SECRET,
                algorithm='HS256'
            )
            
            # Include verification status and details in response
            response_data = {
                'token': token,
                'id': str(doctor_data['_id']),
                'name': doctor_data['name'],
                'email': doctor_data['email'],
                'specialty': doctor_data['specialty'],
                'phone_number': doctor_data.get('phone_number', ''),
                'address': doctor_data.get('address', ''),
                'profile_image': doctor_data.get('profile_image'),
                'is_verified': doctor_data.get('is_verified', False),
                'verification_details': doctor_data.get('verification_details', None),
                'signature': doctor_data.get('signature')  # Add this line
            }
            
            logger.debug("Login successful")  # Add debug log
            return jsonify(response_data), 200
        else:
            logger.debug("Invalid password")  # Add debug log
            return jsonify({'error': 'Invalid credentials'}), 401
            
    except Exception as e:
        logger.error(f"Login error: {str(e)}")  # Add debug log
        return jsonify({'error': 'Server error: ' + str(e)}), 500

@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    try:
        data = request.get_json()
        email = data.get('email')
        
        logger.debug(f"Forgot password request received for email: {email}")
        
        if not email:
            return jsonify({'error': 'Email is required'}), 400

        doctor_data = doctors_collection.find_one({'email': email})
        if not doctor_data:
            logger.debug(f"Email not found: {email}")
            return jsonify({'error': 'Email not found'}), 404

        otp = str(random.randint(100000, 999999))
        logger.debug(f"Generated OTP: {otp}")
        
        if send_otp_email(email, otp):
            doctors_collection.update_one(
                {'email': email},
                {'$set': {
                    'reset_otp': otp,
                    'otp_expiry': datetime.utcnow() + timedelta(minutes=15)
                }}
            )
            logger.debug("OTP sent and saved successfully")
            return jsonify({'message': 'OTP sent successfully'}), 200
        else:
            logger.error("Failed to send OTP email")
            return jsonify({'error': 'Failed to send OTP. Please try again later.'}), 500
    
    except Exception as e:
        logger.error(f"Unexpected error in forgot_password: {str(e)}")
        return jsonify({'error': f'An unexpected error occurred: {str(e)}'}), 500

@app.route('/api/verify-otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    email = data.get('email')
    otp = data.get('otp')
    
    if not email or not otp:
        return jsonify({'error': 'Email and OTP are required'}), 400
        
    result = doctors_collection.find_one({
        'email': email,
        'reset_otp': otp,
        'otp_expiry': {'$gt': datetime.utcnow()}
    })
    
    if not result:
        return jsonify({'error': 'Invalid or expired OTP'}), 400
    
    return jsonify({'message': 'OTP verified successfully'}), 200

@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json()
    email = data.get('email')
    otp = data.get('otp')
    new_password = data.get('newPassword')
    
    if not all([email, otp, new_password]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    doctor_data = doctors_collection.find_one({
        'email': email,
        'reset_otp': otp,
        'otp_expiry': {'$gt': datetime.utcnow()}
    })
    
    if not doctor_data:
        return jsonify({'error': 'Invalid or expired OTP'}), 400

    # Create a Doctor instance and set the new password
    doctor = Doctor.from_dict(doctor_data)
    doctor.set_password(new_password)
    
    # Update the password hash and remove the OTP data
    result = doctors_collection.update_one(
        {'email': email},
        {
            '$set': {'password_hash': doctor.password_hash},
            '$unset': {'reset_otp': '', 'otp_expiry': ''}
        }
    )
    
    if result.modified_count == 0:
        return jsonify({'error': 'Failed to update password'}), 500
        
    return jsonify({'message': 'Password reset successful'}), 200

@app.route('/api/profile', methods=['GET'])
@token_required
def get_profile(user_id):
    doctor_data = doctors_collection.find_one({'_id': ObjectId(user_id)})
    if not doctor_data:
        return jsonify({'error': 'Doctor not found'}), 404
    
    # Make sure to include verification status and signature in response
    response_data = Doctor.from_dict(doctor_data).to_dict()
    response_data.update({
        'is_verified': doctor_data.get('is_verified', False),
        'signature': doctor_data.get('signature')  # Add this line
    })
    return jsonify(response_data), 200

@app.route('/api/change-password', methods=['POST'])
@token_required
def change_password(user_id):
    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')

    if not all([current_password, new_password]):
        return jsonify({'error': 'Both current and new password are required'}), 400

    doctor_data = doctors_collection.find_one({'_id': ObjectId(user_id)})
    if not doctor_data:
        return jsonify({'error': 'Doctor not found'}), 404

    doctor = Doctor.from_dict(doctor_data)
    doctor.password_hash = doctor_data['password_hash']

    if not doctor.check_password(current_password):
        return jsonify({'error': 'Current password is incorrect'}), 400

    # Set and hash the new password
    doctor.set_password(new_password)
    
    # Update the password hash in the database
    result = doctors_collection.update_one(
        {'_id': ObjectId(user_id)},
        {'$set': {'password_hash': doctor.password_hash}}
    )

    if result.modified_count == 0:
        return jsonify({'error': 'Failed to update password'}), 500

    return jsonify({'message': 'Password updated successfully'}), 200

@app.route('/api/update-profile', methods=['PUT'])
@token_required
def update_profile(user_id):
    data = request.get_json()
    
    # Get current doctor data to preserve verification status
    current_doctor = doctors_collection.find_one({'_id': ObjectId(user_id)})
    if not current_doctor:
        return jsonify({'error': 'Doctor not found'}), 404

    update_fields = {
        'name': data.get('name'),
        'specialty': data.get('specialty'),
        'phone_number': data.get('phone_number'),
        'address': data.get('address'),
    }
    
    if data.get('profile_image'):
        update_fields['profile_image'] = data.get('profile_image')

    # Update while preserving verification status
    doctors_collection.update_one(
        {'_id': ObjectId(user_id)}, 
        {'$set': update_fields}
    )
    
    # Get updated doctor data
    updated_doctor = doctors_collection.find_one({'_id': ObjectId(user_id)})
    response_data = Doctor.from_dict(updated_doctor).to_dict()
    
    # Include verification status and details in response
    response_data.update({
        'is_verified': current_doctor.get('is_verified', False),
        'verification_details': current_doctor.get('verification_details'),
        'profile_image': updated_doctor.get('profile_image')
    })
    
    return jsonify(response_data), 200

@app.route('/api/logout', methods=['POST'])
@token_required
def logout(user_id):
    # Optionally blacklist or track tokens here if desired
    return jsonify({'message': 'Logged out successfully'}), 200

@app.route('/api/scan-visit-card', methods=['POST'])
def scan_visit_card():
    data = request.get_json()
    image_data = data.get('image')

    if not image_data:
        return jsonify({'error': 'No image provided'}), 400

    try:
        # Decode base64 image
        image = Image.open(io.BytesIO(base64.b64decode(image_data)))

        # Perform OCR using pytesseract
        text = pytesseract.image_to_string(image)

        # Extract relevant information (this will need to be refined based on visit card format)
        name = extract_name(text)
        email = extract_email(text)
        specialty = extract_specialty(text)
        phone = extract_phone_number(text)  # New helper function

        return jsonify({
            'name': name,
            'email': email,
            'specialty': specialty,
            'phone_number': phone  # Return extracted phone
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/verify-doctor', methods=['POST'])
@token_required
def verify_doctor(user_id):
    try:
        data = request.get_json()
        image_data = data.get('image')

        if not image_data:
            return jsonify({'error': 'No image provided'}), 400

        # Get doctor's data from database
        doctor_data = doctors_collection.find_one({'_id': ObjectId(user_id)})
        if not doctor_data:
            return jsonify({'error': 'Doctor not found'}), 404

        # Get doctor's name from database
        doctor_name = doctor_data['name'].lower().strip()

        logger.debug(f"Checking for Name='{doctor_name}'")

        # Process the image
        image = Image.open(io.BytesIO(base64.b64decode(image_data)))
        
        # Enhance image quality for better OCR
        image = image.convert('L')  # Convert to grayscale
        image = image.point(lambda x: 0 if x < 128 else 255, '1')  # Enhance contrast

        # Extract text from image
        extracted_text = pytesseract.image_to_string(image)
        extracted_text = extracted_text.lower().strip()
        
        logger.debug(f"Extracted text: {extracted_text}")

        # Simple text matching for name
        name_found = doctor_name in extracted_text

        # If name has multiple parts, check each part
        if not name_found:
            name_parts = doctor_name.split()
            name_found = all(part in extracted_text for part in name_parts)

        logger.debug(f"Name found: {name_found}")

        if name_found:
            # Update verification status
            result = doctors_collection.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': {
                    'is_verified': True,
                    'verification_details': {
                        'verified_at': datetime.utcnow(),
                        'matched_text': extracted_text
                    }
                }}
            )
            
            if result.modified_count > 0:
                return jsonify({
                    'verified': True,
                    'message': 'Name verification successful'
                }), 200
            else:
                return jsonify({
                    'error': 'Failed to update verification status'
                }), 500
        else:
            return jsonify({
                'verified': False,
                'error': 'Verification failed: name not found in document',
                'debug_info': {
                    'name_found': name_found,
                    'doctor_name': doctor_name
                }
            }), 400

    except Exception as e:
        logger.error(f"Verification error: {str(e)}")
        return jsonify({'error': f'Verification failed: {str(e)}'}), 500

# Improve the extraction functions
def extract_name(text):
    # Look for patterns that might indicate a name
    # Usually names appear at the beginning or after "Dr." or similar titles
    lines = text.split('\n')
    for line in lines:
        # Look for "Dr." or similar titles
        name_match = re.search(r'(?:Dr\.?|Doctor)\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', line, re.IGNORECASE)
        if name_match:
            return name_match.group(1)
        
        # Look for capitalized words that might be names
        name_match = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', line)
        if name_match:
            return name_match.group(1)
    return ""

def extract_email(text):
    # Implement logic to extract email from text
    # This is a placeholder and needs to be implemented based on the visit card format
    email_match = re.search(r'[\w\.-]+@[\w\.-]+', text)
    if email_match:
        return email_match.group(0)
    return "Extracted Email"

def extract_specialty(text):
    # Common medical specialties
    specialties = [
        'Cardiology', 'Dermatology', 'Neurology', 'Pediatrics', 'Oncology',
        'Orthopedics', 'Gynecology', 'Psychiatry', 'Surgery', 'Internal Medicine',
        # Add more specialties as needed
    ]
    
    lines = text.split('\n')
    for line in lines:
        # Check for known specialties
        for specialty in specialties:
            if specialty.lower() in line.lower():
                return line.strip()
        
        # Look for patterns that might indicate a specialty
        specialty_match = re.search(r'(?:Specialist|Consultant)\s+in\s+([A-Za-z\s]+)', line)
        if specialty_match:
            return specialty_match.group(1).strip()
    return ""

def extract_phone_number(text):
    # Basic pattern to match phone formats, can be refined
    phone_match = re.search(r'(\+?\d[\d\s\-]{7,}\d)', text)
    if phone_match:
        return phone_match.group(0).strip()
    return "Extracted Phone"

@app.route('/api/update-signature', methods=['POST'])
@token_required
def update_signature(user_id):
    try:
        data = request.get_json()
        signature = data.get('signature')

        if not signature:
            return jsonify({'error': 'No signature provided'}), 400

        result = doctors_collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'signature': signature}}
        )

        if result.modified_count > 0:
            # Get updated doctor data
            doctor_data = doctors_collection.find_one({'_id': ObjectId(user_id)})
            return jsonify({
                'message': 'Signature updated successfully',
                'signature': doctor_data.get('signature')
            }), 200
        else:
            return jsonify({'error': 'Failed to update signature'}), 500

    except Exception as e:
        logger.error(f"Signature update error: {str(e)}")
        return jsonify({'error': f'Signature update failed: {str(e)}'}), 500

if __name__ == '__main__':
    # Register with Consul
    try:
        consul_service = ConsulService(Config)
        consul_service.register_service()
        logger.info(f"Registered {Config.SERVICE_NAME} with Consul")
    except Exception as e:
        logger.error(f"Failed to register with Consul: {e}")
        
    app.run(host=Config.HOST, port=Config.PORT, debug=True)
