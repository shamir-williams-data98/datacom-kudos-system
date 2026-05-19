"""
Kudos System — Flask API Server
Provides REST endpoints for the Kudos feature of the Datacom internal portal.
"""

import html
import logging
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)
database.init_db()


@app.route("/")
def serve_index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/users", methods=["GET"])
def get_users():
    return jsonify(database.get_all_users()), 200


@app.route("/api/kudos", methods=["GET"])
def get_kudos():
    page = max(1, request.args.get("page", 1, type=int))
    per_page = max(1, min(50, request.args.get("per_page", 20, type=int)))
    return jsonify(database.get_visible_kudos(page=page, per_page=per_page)), 200


@app.route("/api/kudos", methods=["POST"])
def create_kudos():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request", "details": "JSON body is required."}), 400

    sender_id = data.get("sender_id")
    receiver_id = data.get("receiver_id")
    message = data.get("message", "").strip()

    if not sender_id or not receiver_id:
        return jsonify({"error": "Missing fields", "details": "sender_id and receiver_id are required."}), 400
    if sender_id == receiver_id:
        return jsonify({"error": "Invalid recipient", "details": "You cannot send kudos to yourself."}), 400
    if len(message) < 5:
        return jsonify({"error": "Message too short", "details": "Message must be at least 5 characters."}), 400
    if len(message) > 500:
        return jsonify({"error": "Message too long", "details": "Message must be 500 characters or fewer."}), 400

    sender = database.get_user_by_id(sender_id)
    receiver = database.get_user_by_id(receiver_id)
    if not sender:
        return jsonify({"error": "Invalid sender", "details": "Sender user not found."}), 400
    if not receiver:
        return jsonify({"error": "Invalid recipient", "details": "Recipient user not found."}), 400

    if database.check_duplicate_kudos(sender_id, receiver_id):
        return jsonify({"error": "Duplicate kudos", "details": "You already sent kudos to this person in the last 5 minutes."}), 429

    kudos = database.create_kudos(sender_id, receiver_id, html.escape(message))
    logger.info(f"Kudos created: {sender['name']} -> {receiver['name']}")
    return jsonify(kudos), 201


@app.route("/api/kudos/<int:kudos_id>/hide", methods=["PATCH"])
def hide_kudos(kudos_id):
    data = request.get_json() or {}
    moderated_by = data.get("moderated_by")
    reason = data.get("reason", "").strip()
    if not moderated_by:
        return jsonify({"error": "Missing field", "details": "moderated_by is required."}), 400
    admin = database.get_user_by_id(moderated_by)
    if not admin or admin["role"] != "admin":
        return jsonify({"error": "Unauthorized", "details": "Only administrators can moderate kudos."}), 403
    database.hide_kudos(kudos_id, moderated_by, reason if reason else None)
    logger.info(f"Kudos {kudos_id} hidden by {admin['name']}")
    return jsonify({"message": "Kudos hidden successfully."}), 200


@app.route("/api/kudos/<int:kudos_id>/restore", methods=["PATCH"])
def restore_kudos(kudos_id):
    data = request.get_json() or {}
    moderated_by = data.get("moderated_by")
    if not moderated_by:
        return jsonify({"error": "Missing field", "details": "moderated_by is required."}), 400
    admin = database.get_user_by_id(moderated_by)
    if not admin or admin["role"] != "admin":
        return jsonify({"error": "Unauthorized", "details": "Only administrators can moderate kudos."}), 403
    database.restore_kudos(kudos_id)
    logger.info(f"Kudos {kudos_id} restored by {admin['name']}")
    return jsonify({"message": "Kudos restored successfully."}), 200


@app.route("/api/kudos/<int:kudos_id>", methods=["DELETE"])
def delete_kudos(kudos_id):
    moderated_by = request.args.get("moderated_by", type=int)
    if not moderated_by:
        return jsonify({"error": "Missing field", "details": "moderated_by query param is required."}), 400
    admin = database.get_user_by_id(moderated_by)
    if not admin or admin["role"] != "admin":
        return jsonify({"error": "Unauthorized", "details": "Only administrators can delete kudos."}), 403
    database.delete_kudos(kudos_id)
    logger.info(f"Kudos {kudos_id} deleted by {admin['name']}")
    return jsonify({"message": "Kudos deleted permanently."}), 200


@app.route("/api/kudos/hidden", methods=["GET"])
def get_hidden_kudos():
    return jsonify(database.get_hidden_kudos()), 200


if __name__ == "__main__":
    logger.info("Starting Kudos System on http://localhost:5000")
    app.run(debug=True, port=5000)
