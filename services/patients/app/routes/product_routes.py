from flask import Blueprint, request, jsonify

product_bp = Blueprint("product", __name__)

@product_bp.route("/products", methods=["GET"])
def get_all_products():
    return jsonify({"message": "API is working!"})
