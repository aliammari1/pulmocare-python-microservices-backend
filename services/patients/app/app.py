import inspect
import os
import random
import smtplib
import sys
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from functools import wraps

import jwt
from bson import ObjectId
from decorator.health_check import health_check_middleware
from dotenv import load_dotenv
from flask import Flask, jsonify, make_response, request
from flask_cors import CORS
from models.patient import Patient

# Add OpenTelemetry imports at the top
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pymongo import MongoClient
from services.logger_service import logger_service
from services.mongodb_client import MongoDBClient
from services.prometheus_service import PrometheusService
from services.rabbitmq_client import RabbitMQClient
from services.redis_client import RedisClient
from services.tracing_service import TracingService

from config import Config

# Determine environment and load corresponding .env file
env = os.getenv("ENV", "development")
dotenv_file = f".env.{env}"
if not os.path.exists(dotenv_file):
    dotenv_file = ".env"
load_dotenv(dotenv_path=dotenv_file)


# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Initialize OpenTelemetry instrumentations
FlaskInstrumentor().instrument_app(app)
PymongoInstrumentor().instrument()
RequestsInstrumentor().instrument()
RedisInstrumentor().instrument()

# Apply health check middleware
app = health_check_middleware(Config)(app)

# Initialize services
tracing_service = TracingService(app)
redis_client = RedisClient(Config)
mongodb_client = MongoDBClient(Config)
rabbitmq_client = RabbitMQClient(Config)
prometheus_service = PrometheusService(app, Config)


print("Patient class: ", Patient)
# MongoDB configuration
client = MongoClient(
    "mongodb://admin:admin@localhost:27017/"
)  # Adjust if using a different host/port
db = client["medapp"]  # Use your database name
patients_collection = db["patients"]

print("MongoDB Connection Successful")

JWT_SECRET = os.getenv("JWT_SECRET", "replace-with-strong-secret")


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return jsonify({"error": "Token missing"}), 401
        token = auth_header.split()[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            user_id = payload["user_id"]
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(user_id, *args, **kwargs)

    return decorated


def send_otp_email(to_email, otp):
    try:
        sender_email = os.getenv("EMAIL_ADDRESS")
        sender_password = os.getenv("EMAIL_PASSWORD")

        logger_service.warning(
            f"Email config - Address: {sender_email}, Password length: {len(sender_password) if sender_password else 0}"
        )

        if not sender_email or not sender_password:
            logger_service.error("Email configuration missing in .env file")
            return False

        msg = MIMEText(
            f"Your OTP code for password reset is: {otp}\nThis code will expire in 15 minutes."
        )
        msg["Subject"] = "Medicare - Password Reset OTP"
        msg["From"] = sender_email
        msg["To"] = to_email

        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                smtp.login(sender_email, sender_password)
                smtp.send_message(msg)
                logger_service.warning(f"OTP email sent successfully to {to_email}")
                return True
        except smtplib.SMTPAuthenticationError as e:
            logger_service.error(f"Gmail authentication failed: {str(e)}")
            return False

    except Exception as e:
        logger_service.error(f"Error sending email: {str(e)}")
        return False


@app.route("/api/patient/signup", methods=["POST"])
def patient_signup():
    try:
        data = request.get_json()
        print(f"Received data: {data}")

        if not data:
            return jsonify({"error": "No data provided"}), 400

        required_fields = ["name", "email", "password"]
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return (
                jsonify(
                    {"error": f'Missing required fields: {", ".join(missing_fields)}'}
                ),
                400,
            )

        if patients_collection.find_one({"email": data["email"]}):
            return jsonify({"error": "Email already registered"}), 400

        patient_id = str(ObjectId())

        # Create patient with correct parameters
        patient = Patient(
            id=patient_id,
            name=data["name"],
            email=data["email"],
            phoneNumber=data.get("phoneNumber"),
            password=data["password"],  # This will be hashed by the constructor
        )

        # Convert to dict and insert
        patient_dict = patient.to_dict()
        result = patients_collection.insert_one(patient_dict)

        # Prepare response
        response_data = patient_dict.copy()
        del response_data["password_hash"]
        response_data["_id"] = str(result.inserted_id)

        return jsonify(response_data), 201

    except Exception as e:
        logger_service.error(f"Error in patient_signup: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@app.route("/api/patient/login", methods=["POST"])
def patient_login():
    from werkzeug.security import check_password_hash

    data = request.get_json()
    patient_data = patients_collection.find_one({"email": data["email"]})

    if not patient_data:
        return jsonify({"error": "Invalid credentials"}), 401

    # Use check_password_hash directly since your Patient class doesn't have this method
    if check_password_hash(patient_data["password_hash"], data["password"]):
        token = jwt.encode(
            {
                "user_id": str(patient_data["_id"]),
                "exp": datetime.utcnow() + timedelta(days=1),
            },
            JWT_SECRET,
            algorithm="HS256",
        )
        return (
            jsonify(
                {
                    "token": token,
                    "id": str(patient_data["_id"]),
                    "name": patient_data["name"],
                    "email": patient_data["email"],
                }
            ),
            200,
        )

    return jsonify({"error": "Invalid credentials"}), 401


@app.route("/api/patient/forgot-password", methods=["POST"])
def patient_forgot_password():
    try:
        data = request.get_json()
        email = data.get("email")

        logger_service.debug(f"Forgot password request received for email: {email}")

        if not email:
            return jsonify({"error": "Email is required"}), 400

        patient_data = patients_collection.find_one({"email": email})
        if not patient_data:
            logger_service.debug(f"Email not found: {email}")
            return jsonify({"error": "Email not found"}), 404

        otp = str(random.randint(100000, 999999))
        logger_service.debug(f"Generated OTP: {otp}")
        if send_otp_email(email, otp):
            patients_collection.update_one(
                {"email": email},
                {
                    "$set": {
                        "reset_otp": otp,
                        "otp_expiry": datetime.utcnow() + timedelta(minutes=15),
                    }
                },
            )
            logger_service.debug("OTP sent and saved successfully")
            return jsonify({"message": "OTP sent successfully"}), 200
        else:
            logger_service.error("Failed to send OTP email")
            return jsonify({"error": "Failed to send OTP email"}), 500

    except Exception as e:
        logger_service.error(f"Error in forgot_password: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/patient/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json()
    email, otp = data.get("email"), data.get("otp")
    result = patients_collection.find_one(
        {"email": email, "reset_otp": otp, "otp_expiry": {"$gt": datetime.utcnow()}}
    )
    if not result:
        return jsonify({"error": "Invalid or expired OTP"}), 400
    return jsonify({"message": "OTP verified successfully"}), 200


@app.route("/api/patient/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json()
    email, otp, new_password = (
        data.get("email"),
        data.get("otp"),
        data.get("newPassword"),
    )
    patient_data = patients_collection.find_one(
        {"email": email, "reset_otp": otp, "otp_expiry": {"$gt": datetime.utcnow()}}
    )
    if not patient_data:
        return jsonify({"error": "Invalid or expired OTP"}), 400
    patient = Patient.from_dict(patient_data)
    patient.set_password(new_password)  # Ensure password is hashed here
    patients_collection.update_one(
        {"email": email},
        {
            "$set": {"password_hash": patient.password_hash},
            "$unset": {"reset_otp": "", "otp_expiry": ""},
        },
    )
    return jsonify({"message": "Password reset successful"}), 200


@app.route("/api/test-email-config", methods=["GET"])
def test_email_config():
    sender_email = os.getenv("EMAIL_ADDRESS")
    sender_password = os.getenv("EMAIL_PASSWORD")

    config_info = {
        "email_configured": bool(sender_email and sender_password),
        "email_address": sender_email,
        "password_length": len(sender_password) if sender_password else 0,
    }

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender_email, sender_password)
            config_info["smtp_login"] = "successful"
    except Exception as e:
        config_info["smtp_login"] = "failed"
        config_info["error"] = str(e)

    return jsonify(config_info)


@app.route("/api/patient/list", methods=["GET"])
def get_all_patients():
    try:
        # Get all patients from MongoDB
        patients_list = list(
            patients_collection.find(
                {}, {"password_hash": 0, "reset_otp": 0, "otp_expiry": 0}
            )
        )

        # Convert ObjectId to string for JSON serialization
        for patient in patients_list:
            patient["_id"] = str(patient["_id"])

        return jsonify(patients_list), 200
    except Exception as e:
        logger_service.error(f"Error getting patients list: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    app.run(host=Config.HOST, port=Config.PORT, debug=True)
