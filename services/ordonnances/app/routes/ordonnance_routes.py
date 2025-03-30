import datetime
import json  # Ajout de l'import manquant
import os
import traceback  # Pour le stack trace détaillé

from bson import ObjectId
from flask import Blueprint, jsonify, make_response, request, send_file
from models.ordonnance import Ordonnance
from services.logger_service import logger_service
from services.mongodb_client import MongoDBClient
from services.pdf_service import generate_ordonnance_pdf

from config import Config

# Configure logger


ordonnance_bp = Blueprint("ordonnances", __name__)
db = MongoDBClient(Config).db


@ordonnance_bp.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.update(
            {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Accept, Authorization",
                "Access-Control-Max-Age": "120",
            }
        )
        return response


@ordonnance_bp.after_request
def after_request(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
    return response


# Correction des routes pour correspondre au frontend
@ordonnance_bp.route("", methods=["POST"])  # Changed from '/' to ''
def create_ordonnance():
    try:
        data = request.get_json()
        print("Received data:", data)  # Debug print

        # Valider les champs requis
        required_fields = ["patient_id", "medecin_id", "medicaments"]
        if not all(field in data for field in required_fields):
            missing = [f for f in required_fields if f not in data]
            return jsonify({"error": f"Champs manquants: {', '.join(missing)}"}), 400

        # Créer l'ordonnance
        ordonnance = {
            "patient_id": data["patient_id"],
            "medecin_id": data["medecin_id"],
            "medicaments": data["medicaments"],
            "clinique": data.get("clinique", ""),
            "specialite": data.get("specialite", ""),
            "date": datetime.datetime.now().isoformat(),
        }

        # Sauvegarder dans MongoDB
        result = db.ordonnances.insert_one(ordonnance)

        return (
            jsonify(
                {
                    "id": str(result.inserted_id),
                    "message": "Ordonnance créée avec succès",
                }
            ),
            201,
        )

    except Exception as e:
        print("Error:", str(e))  # Debug print
        return jsonify({"error": str(e)}), 500


@ordonnance_bp.route("/", methods=["GET"])
def get_ordonnances():
    ordonnances = list(db.ordonnances.find())
    for ord in ordonnances:
        ord["_id"] = str(ord["_id"])
    return jsonify(ordonnances)


@ordonnance_bp.route("/medecin/<medecin_id>/ordonnances", methods=["GET"])
def get_medecin_ordonnances(medecin_id):
    try:
        ordonnances = list(db.ordonnances.find({"medecin_id": medecin_id}))
        for ord in ordonnances:
            ord["_id"] = str(ord["_id"])
            if isinstance(ord.get("date"), datetime.datetime):
                ord["date"] = ord["date"].isoformat()

            # Vérifier si un PDF existe pour cette ordonnance
            pdf_doc = db.pdf_files.find_one({"ordonnance_id": str(ord["_id"])})
            ord["has_pdf"] = pdf_doc is not None
            if pdf_doc:
                ord["pdf_filename"] = pdf_doc["filename"]

        return jsonify(ordonnances)
    except Exception as e:
        print(f"Erreur lors de la récupération des ordonnances: {e}")
        return jsonify({"error": str(e)}), 500


@ordonnance_bp.route("/ordonnances/<id>/pdf", methods=["POST"])
def save_ordonnance_pdf(id):
    try:
        ordonnance = db.ordonnances.find_one({"_id": ObjectId(id)})
        if not ordonnance:
            return jsonify({"error": "Ordonnance non trouvée"}), 404

        pdf_bytes = request.files["pdf"].read()
        filename = pdf_service.save_pdf(
            ordonnance["medecin_id"], pdf_bytes, str(ordonnance["_id"])
        )

        return jsonify({"message": "PDF sauvegardé", "filename": filename}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@ordonnance_bp.route("/ordonnance/<id>", methods=["GET"])
def get_ordonnance(id):
    try:
        # Validate ObjectId format
        try:
            obj_id = ObjectId(id)
        except bson.errors.InvalidId:
            return jsonify({"error": "Invalid ordonnance ID format"}), 400

        ordonnance = db.ordonnances.find_one({"_id": obj_id})
        if not ordonnance:
            return jsonify({"error": "Ordonnance not found"}), 404

        ordonnance["_id"] = str(ordonnance["_id"])
        pdf_info = db.pdf_files.find_one({"ordonnance_id": str(ordonnance["_id"])})
        ordonnance["has_pdf"] = pdf_info is not None
        if pdf_info:
            ordonnance["pdf_filename"] = pdf_info["filename"]
        return jsonify(ordonnance)
    except Exception as e:
        print(f"Error fetching ordonnance {id}: {str(e)}")
        return jsonify({"error": "Erreur lors de la récupération de l'ordonnance"}), 500


@ordonnance_bp.route("/<ordonnance_id>/pdf", methods=["GET"])
def get_ordonnance_pdf(ordonnance_id):
    try:
        ordonnance = db.ordonnances.find_one({"_id": ObjectId(ordonnance_id)})
        if not ordonnance:
            return jsonify({"error": "Ordonnance non trouvée"}), 404

        # Chercher d'abord le PDF existant
        pdf_doc = db.pdf_files.find_one({"ordonnance_id": ordonnance_id})
        if pdf_doc and os.path.exists(pdf_doc["path"]):
            return send_file(pdf_doc["path"], mimetype="application/pdf")

        # Si pas de PDF existant, en générer un nouveau
        pdf_path = generate_ordonnance_pdf(ordonnance)

        # Sauvegarder la référence du PDF
        db.pdf_files.insert_one(
            {
                "ordonnance_id": ordonnance_id,
                "filename": f"ordonnance_{ordonnance_id}.pdf",
                "path": pdf_path,
                "created_at": datetime.datetime.now(),
            }
        )

        return send_file(pdf_path, mimetype="application/pdf")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@ordonnance_bp.errorhandler(Exception)
def handle_error(error):
    response = {"error": str(error), "status": "error"}
    return jsonify(response), 500


@ordonnance_bp.route("/ordonnances/<id>/verify", methods=["GET"])
def verify_ordonnance(id):
    try:
        ordonnance = db.ordonnances.find_one({"_id": ObjectId(id)})
        if not ordonnance:
            return (
                jsonify({"status": "error", "message": "Ordonnance non trouvée"}),
                404,
            )

        # Vérification de base
        is_valid = (
            ordonnance.get("patient_id")
            and ordonnance.get("medecin_id")
            and ordonnance.get("medicaments")
        )

        return jsonify(
            {
                "status": "success",
                "is_valid": is_valid,
                "ordonnance_id": str(ordonnance["_id"]),
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@ordonnance_bp.route("/test", methods=["GET"])
def test_connection():
    return jsonify({"status": "success", "message": "API is working"}), 200
