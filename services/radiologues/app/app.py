import base64
import io
import os
import random
import re
import smtplib
import socket
import uuid
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from functools import wraps

import jwt
import pytesseract
import requests
from bs4 import BeautifulSoup
from bson import ObjectId
from decorator.health_check import health_check_middleware
from dotenv import load_dotenv
from flask import Flask, jsonify, make_response, request, send_file
from flask_cors import CORS
from fpdf import FPDF
from models.radiologue import Radiologue

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
from PIL import Image
from pymongo import DESCENDING, MongoClient
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
# MongoDB configuration
client = MongoClient(os.getenv("MONGODB_URI", "mongodb://admin:admin@localhost:27017/"))
db = client.medapp
radiologues_collection = db.radiologues
# Ajout pour les rapports
rapports_collection = db.rapports
# Medtn
medtn_radiologues_collection = db["medtn_radiologues"]


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
        except:
            return jsonify({"error": "Invalid token"}), 401
        return f(user_id, *args, **kwargs)

    return decorated


def send_otp_email(to_email, otp):
    try:
        sender_email = os.getenv("EMAIL_ADDRESS")
        sender_password = os.getenv("EMAIL_PASSWORD")

        logger_service.debug(
            f"Email configuration - Sender: {sender_email}, Password length: {len(sender_password) if sender_password else 0}"
        )

        if not sender_email or not sender_password:
            logger_service.error("Email configuration missing")
            raise Exception("Email configuration missing")

        msg = MIMEText(
            f"""
        Hello,

        Your OTP code for password reset is: {otp}

        This code will expire in 15 minutes.
        If you did not request this code, please ignore this email.

        Best regards,
        Medicare Team
        """
        )

        msg["Subject"] = "Medicare - Password Reset OTP"
        msg["From"] = sender_email
        msg["To"] = to_email

        try:
            logger_service.debug("Attempting SMTP connection to smtp.gmail.com:465")
            smtp = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10)
            logger_service.debug("SMTP connection successful")

            logger_service.debug("Attempting SMTP login")
            smtp.login(sender_email, sender_password)
            logger_service.debug("SMTP login successful")

            logger_service.debug("Sending email")
            smtp.send_message(msg)
            logger_service.debug("Email sent successfully")

            smtp.quit()
            return True

        except smtplib.SMTPAuthenticationError as auth_error:
            logger_service.error(
                f"SMTP Authentication failed - Details: {str(auth_error)}"
            )
            raise Exception(
                f"Email authentication failed. Please check your credentials."
            )

        except smtplib.SMTPException as smtp_error:
            logger_service.error(f"SMTP error occurred: {str(smtp_error)}")
            raise Exception(f"Email sending failed: {str(smtp_error)}")

        except Exception as e:
            logger_service.error(f"Unexpected SMTP error: {str(e)}")
            raise Exception(f"Unexpected error while sending email: {str(e)}")

    except Exception as e:
        logger_service.error(f"Email sending error: {str(e)}")
        return False


@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.get_json()

    if radiologues_collection.find_one({"email": data["email"]}):
        return jsonify({"error": "Email already registered"}), 400

    radiologue = Radiologue(
        name=data["name"],
        email=data["email"],
        specialty=data["specialty"],
        phone_number=data["phoneNumber"],
        address=data["address"],
        password=data["password"],
    )

    # Insert the radiologue document with is_verified field
    result = radiologues_collection.insert_one(
        {
            "_id": radiologue._id,
            "name": radiologue.name,
            "email": radiologue.email,
            "password_hash": radiologue.password_hash,
            "specialty": radiologue.specialty,
            "phone_number": radiologue.phone_number,
            "address": radiologue.address,
            "is_verified": False,  # Add default verification status
        }
    )

    return jsonify(radiologue.to_dict()), 201


@app.route("/api/login", methods=["POST"])
def login():
    try:
        data = request.get_json()
        logger_service.debug(
            f"Login attempt for email: {data.get('email')}"
        )  # Add debug log

        if not data or "email" not in data or "password" not in data:
            return jsonify({"error": "Email and password are required"}), 400

        radiologue_data = radiologues_collection.find_one({"email": data["email"]})
        if not radiologue_data:
            logger_service.debug("Email not found")  # Add debug log
            return jsonify({"error": "Invalid credentials"}), 401

        radiologue = Radiologue.from_dict(radiologue_data)
        radiologue.password_hash = radiologue_data["password_hash"]

        if radiologue.check_password(data["password"]):
            token = jwt.encode(
                {
                    "user_id": str(radiologue_data["_id"]),
                    "exp": datetime.utcnow() + timedelta(days=1),
                },
                JWT_SECRET,
                algorithm="HS256",
            )

            # Include verification status and details in response
            response_data = {
                "token": token,
                "id": str(radiologue_data["_id"]),
                "name": radiologue_data["name"],
                "email": radiologue_data["email"],
                "specialty": radiologue_data["specialty"],
                "phone_number": radiologue_data.get("phone_number", ""),
                "address": radiologue_data.get("address", ""),
                "profile_image": radiologue_data.get("profile_image"),
                "is_verified": radiologue_data.get("is_verified", False),
                "verification_details": radiologue_data.get(
                    "verification_details", None
                ),
            }

            logger_service.debug("Login successful")  # Add debug log
            return jsonify(response_data), 200
        else:
            logger_service.debug("Invalid password")  # Add debug log
            return jsonify({"error": "Invalid credentials"}), 401

    except Exception as e:
        logger_service.error(f"Login error: {str(e)}")  # Add debug log
        return jsonify({"error": "Server error: " + str(e)}), 500


@app.route("/api/forgot-password", methods=["POST"])
def forgot_password():
    try:
        data = request.get_json()
        email = data.get("email")

        logger_service.debug(f"Forgot password request received for email: {email}")

        if not email:
            return jsonify({"error": "Email is required"}), 400

        radiologue_data = radiologues_collection.find_one({"email": email})
        if not radiologue_data:
            logger_service.debug(f"Email not found: {email}")
            return jsonify({"error": "Email not found"}), 404

        otp = str(random.randint(100000, 999999))
        logger_service.debug(f"Generated OTP: {otp}")

        if send_otp_email(email, otp):
            radiologues_collection.update_one(
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
            return (
                jsonify({"error": "Failed to send OTP. Please try again later."}),
                500,
            )

    except Exception as e:
        logger_service.error(f"Unexpected error in forgot_password: {str(e)}")
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500


@app.route("/api/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json()
    email = data.get("email")
    otp = data.get("otp")

    if not email or not otp:
        return jsonify({"error": "Email and OTP are required"}), 400

    result = radiologues_collection.find_one(
        {"email": email, "reset_otp": otp, "otp_expiry": {"$gt": datetime.utcnow()}}
    )

    if not result:
        return jsonify({"error": "Invalid or expired OTP"}), 400

    return jsonify({"message": "OTP verified successfully"}), 200


@app.route("/api/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json()
    email = data.get("email")
    otp = data.get("otp")
    new_password = data.get("newPassword")

    if not all([email, otp, new_password]):
        return jsonify({"error": "Missing required fields"}), 400

    radiologue_data = radiologues_collection.find_one(
        {"email": email, "reset_otp": otp, "otp_expiry": {"$gt": datetime.utcnow()}}
    )

    if not radiologue_data:
        return jsonify({"error": "Invalid or expired OTP"}), 400

    # Create a Radiologue instance and set the new password
    radiologue = Radiologue.from_dict(radiologue_data)
    radiologue.set_password(new_password)

    # Update the password hash and remove the OTP data
    result = radiologues_collection.update_one(
        {"email": email},
        {
            "$set": {"password_hash": radiologue.password_hash},
            "$unset": {"reset_otp": "", "otp_expiry": ""},
        },
    )

    if result.modified_count == 0:
        return jsonify({"error": "Failed to update password"}), 500

    return jsonify({"message": "Password reset successful"}), 200


@app.route("/api/profile", methods=["GET"])
@token_required
def get_profile(user_id):
    radiologue_data = radiologues_collection.find_one({"_id": ObjectId(user_id)})
    if not radiologue_data:
        return jsonify({"error": "Radiologue not found"}), 404

    # Make sure to include verification status in response
    response_data = Radiologue.from_dict(radiologue_data).to_dict()
    response_data["is_verified"] = radiologue_data.get("is_verified", False)
    return jsonify(response_data), 200


# API Pour AFFICHER tout les docteurs du base de donnée
@app.route("/api/radiologues", methods=["GET"])
def get_radiologues():
    try:
        radiologues = radiologues_collection.find()
        radiologues_list = [Radiologue.from_dict(doc).to_dict() for doc in radiologues]
        return jsonify(radiologues_list), 200
    except Exception as e:
        return (
            jsonify(
                {"error": f"Erreur lors de la récupération des docteurs : {str(e)}"}
            ),
            500,
        )


@app.route("/api/change-password", methods=["POST"])
@token_required
def change_password(user_id):
    data = request.get_json()
    current_password = data.get("current_password")
    new_password = data.get("new_password")

    if not all([current_password, new_password]):
        return jsonify({"error": "Both current and new password are required"}), 400

    radiologue_data = radiologues_collection.find_one({"_id": ObjectId(user_id)})
    if not radiologue_data:
        return jsonify({"error": "Radiologue not found"}), 404

    radiologue = Radiologue.from_dict(radiologue_data)
    radiologue.password_hash = radiologue_data["password_hash"]

    if not radiologue.check_password(current_password):
        return jsonify({"error": "Current password is incorrect"}), 400

    # Set and hash the new password
    radiologue.set_password(new_password)

    # Update the password hash in the database
    result = radiologues_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"password_hash": radiologue.password_hash}},
    )

    if result.modified_count == 0:
        return jsonify({"error": "Failed to update password"}), 500

    return jsonify({"message": "Password updated successfully"}), 200


@app.route("/api/update-profile", methods=["PUT"])
@token_required
def update_profile(user_id):
    data = request.get_json()

    # Get current radiologue data to preserve verification status
    current_radiologue = radiologues_collection.find_one({"_id": ObjectId(user_id)})
    if not current_radiologue:
        return jsonify({"error": "Radiologue not found"}), 404

    update_fields = {
        "name": data.get("name"),
        "specialty": data.get("specialty"),
        "phone_number": data.get("phone_number"),
        "address": data.get("address"),
    }

    if data.get("profile_image"):
        update_fields["profile_image"] = data.get("profile_image")

    # Update while preserving verification status
    radiologues_collection.update_one(
        {"_id": ObjectId(user_id)}, {"$set": update_fields}
    )

    # Get updated radiologue data
    updated_radiologue = radiologues_collection.find_one({"_id": ObjectId(user_id)})
    response_data = Radiologue.from_dict(updated_radiologue).to_dict()

    # Include verification status and details in response
    response_data.update(
        {
            "is_verified": current_radiologue.get("is_verified", False),
            "verification_details": current_radiologue.get("verification_details"),
            "profile_image": updated_radiologue.get("profile_image"),
        }
    )

    return jsonify(response_data), 200


@app.route("/api/logout", methods=["POST"])
@token_required
def logout(user_id):
    # Optionally blacklist or track tokens here if desired
    return jsonify({"message": "Logged out successfully"}), 200


@app.route("/api/scan-visit-card", methods=["POST"])
def scan_visit_card():
    data = request.get_json()
    image_data = data.get("image")

    if not image_data:
        return jsonify({"error": "No image provided"}), 400

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

        return (
            jsonify(
                {
                    "name": name,
                    "email": email,
                    "specialty": specialty,
                    "phone_number": phone,  # Return extracted phone
                }
            ),
            200,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Repport API
@app.route("/api/rapport", methods=["POST"])
def ajouter_rapport():
    data = request.json

    if not data:
        return jsonify({"error": "Données manquantes"}), 400

    rapport = {
        "patientName": data["patientName"],
        "examType": data["examType"],
        "reportType": data["reportType"],
        "content": data["content"],
        "date": datetime.utcnow(),
        "status": "pending_analysis",
    }

    try:
        # Insert report
        result = rapports_collection.insert_one(rapport)
        report_id = str(result.inserted_id)

        # Publish event for analysis
        rabbitmq_client = RabbitMQClient(Config)
        rabbitmq_client.publish_radiology_report(
            report_id,
            {
                "patientName": data["patientName"],
                "examType": data["examType"],
                "reportType": data["reportType"],
                "content": data["content"],
            },
        )
        rabbitmq_client.close()

        return (
            jsonify({"message": "Rapport ajouté avec succès", "rapport_id": report_id}),
            201,
        )
    except Exception as e:
        logger_service.error(f"Error creating report: {str(e)}")
        return jsonify({"error": "Failed to create report", "details": str(e)}), 500


@app.route("/api/rapports", methods=["GET"])
def afficher_rapports():
    """Récupère tous les rapports triés par date descendante."""
    try:
        rapports = rapports_collection.find().sort("date", DESCENDING)
        rapport_list = []

        for rapport in rapports:
            print(rapport)  # Debug : Afficher chaque rapport pour voir son format
            rapport_list.append(
                {
                    "_id": str(rapport["_id"]),
                    "patientName": rapport.get("patientName", "Inconnu"),
                    "examType": rapport.get("examType", "Non spécifié"),
                    "reportType": rapport.get("reportType", "Non spécifié"),
                    "content": rapport.get("content", "Aucun contenu"),
                    "date": (
                        str(rapport["date"]) if "date" in rapport else None
                    ),  # Conversion sûre
                }
            )

        return jsonify(rapport_list), 200

    except Exception as e:
        print(f"Erreur lors de la récupération des rapports: {e}")  # Afficher l'erreur
        return jsonify({"error": "Une erreur est survenue", "details": str(e)}), 500


@app.route("/api/verify-radiologue", methods=["POST"])
@token_required
def verify_radiologue(user_id):
    try:
        data = request.get_json()
        image_data = data.get("image")

        if not image_data:
            return jsonify({"error": "No image provided"}), 400

        # Get radiologue's data from database
        radiologue_data = radiologues_collection.find_one({"_id": ObjectId(user_id)})
        if not radiologue_data:
            return jsonify({"error": "Radiologue not found"}), 404

        # Get radiologue's name from database
        radiologue_name = radiologue_data["name"].lower().strip()

        logger_service.debug(f"Checking for Name='{radiologue_name}'")

        # Process the image
        image = Image.open(io.BytesIO(base64.b64decode(image_data)))

        # Enhance image quality for better OCR
        image = image.convert("L")  # Convert to grayscale
        image = image.point(lambda x: 0 if x < 128 else 255, "1")  # Enhance contrast

        # Extract text from image
        extracted_text = pytesseract.image_to_string(image)
        extracted_text = extracted_text.lower().strip()

        logger_service.debug(f"Extracted text: {extracted_text}")

        # Simple text matching for name
        name_found = radiologue_name in extracted_text

        # If name has multiple parts, check each part
        if not name_found:
            name_parts = radiologue_name.split()
            name_found = all(part in extracted_text for part in name_parts)

        logger_service.debug(f"Name found: {name_found}")

        if name_found:
            # Update verification status
            result = radiologues_collection.update_one(
                {"_id": ObjectId(user_id)},
                {
                    "$set": {
                        "is_verified": True,
                        "verification_details": {
                            "verified_at": datetime.utcnow(),
                            "matched_text": extracted_text,
                        },
                    }
                },
            )

            if result.modified_count > 0:
                return (
                    jsonify(
                        {"verified": True, "message": "Name verification successful"}
                    ),
                    200,
                )
            else:
                return jsonify({"error": "Failed to update verification status"}), 500
        else:
            return (
                jsonify(
                    {
                        "verified": False,
                        "error": "Verification failed: name not found in document",
                        "debug_info": {
                            "name_found": name_found,
                            "radiologue_name": radiologue_name,
                        },
                    }
                ),
                400,
            )

    except Exception as e:
        logger_service.error(f"Verification error: {str(e)}")
        return jsonify({"error": f"Verification failed: {str(e)}"}), 500


# Improve the extraction functions
def extract_name(text):
    # Look for patterns that might indicate a name
    # Usually names appear at the beginning or after "Dr." or similar titles
    lines = text.split("\n")
    for line in lines:
        # Look for "Dr." or similar titles
        name_match = re.search(
            r"(?:Dr\.?|Radiologue)\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
            line,
            re.IGNORECASE,
        )
        if name_match:
            return name_match.group(1)

        # Look for capitalized words that might be names
        name_match = re.search(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", line)
        if name_match:
            return name_match.group(1)
    return ""


def extract_email(text):
    # Implement logic to extract email from text
    # This is a placeholder and needs to be implemented based on the visit card format
    email_match = re.search(r"[\w\.-]+@[\w\.-]+", text)
    if email_match:
        return email_match.group(0)
    return "Extracted Email"


def extract_specialty(text):
    # Common medical specialties
    specialties = [
        "Cardiology",
        "Dermatology",
        "Neurology",
        "Pediatrics",
        "Oncology",
        "Orthopedics",
        "Gynecology",
        "Psychiatry",
        "Surgery",
        "Internal Medicine",
        # Add more specialties as needed
    ]

    lines = text.split("\n")
    for line in lines:
        # Check for known specialties
        for specialty in specialties:
            if specialty.lower() in line.lower():
                return line.strip()

        # Look for patterns that might indicate a specialty
        specialty_match = re.search(
            r"(?:Specialist|Consultant)\s+in\s+([A-Za-z\s]+)", line
        )
        if specialty_match:
            return specialty_match.group(1).strip()
    return ""


def extract_phone_number(text):
    # Basic pattern to match phone formats, can be refined
    phone_match = re.search(r"(\+?\d[\d\s\-]{7,}\d)", text)
    if phone_match:
        return phone_match.group(0).strip()
    return "Extracted Phone"


# API POUR TELECHARGER PDF RAPPORT
@app.route("/api/generate-pdf", methods=["GET"])
def generate_pdf():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Rapport Médical", ln=True, align="C")
    pdf.cell(200, 10, txt="Patient: John Doe", ln=True, align="L")
    pdf.cell(200, 10, txt="Type d'examen: Radiographie", ln=True, align="L")
    pdf.cell(200, 10, txt="Date: 2023-10-01", ln=True, align="L")
    pdf.output("rapport.pdf")
    return send_file("rapport.pdf", as_attachment=True)


# API POUR SCRAPING
def scrape_medtn_radiologues():
    base_url = "https://www.med.tn/medecin"
    response = requests.get(base_url)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        radiologues = []
        for radiologue_card in soup.find_all("div", class_="radiologue-card"):
            name = radiologue_card.find("h2").text.strip()
            specialty = radiologue_card.find("p", class_="specialty").text.strip()
            location = radiologue_card.find("p", class_="location").text.strip()
            profile_url = radiologue_card.find("a", class_="profile-link")["href"]
            radiologue = {
                "name": name,
                "specialty": specialty,
                "location": location,
                "profile_url": profile_url,
            }
            radiologues.append(radiologue)
        return radiologues
    else:
        print(f"Failed to retrieve data: {response.status_code}")
        return []


@app.route("/api/scrape_radiologues", methods=["GET"])
def scrape_and_store_radiologues():
    radiologues = scrape_medtn_radiologues()
    if radiologues:
        medtn_radiologues_collection.insert_many(radiologues)
        return jsonify({"message": "Données des médecins insérées avec succès."}), 200
    else:
        return jsonify({"message": "Aucune donnée à insérer."}), 400


@app.route("/api/radiologues_med", methods=["GET"])
def get_radiologues_med():
    radiologues = list(medtn_radiologues_collection.find({}, {"_id": 0}))
    return jsonify(radiologues)


if __name__ == "__main__":
    app.run(host=Config.HOST, port=Config.PORT, debug=True)
