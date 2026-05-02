"""REST API — all routes require an admin session cookie."""

import csv
import io
import sqlite3
import threading

import bcrypt
from flask import Blueprint, current_app, g, jsonify, request, Response

from src import database as db
from src.web.auth import require_admin

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _conn():
    return current_app.config["DB_CONN"]


def _handler():
    return current_app.config.get("CARD_HANDLER")


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@api_bp.route("/users", methods=["GET"])
@require_admin
def list_users():
    users = db.list_users(_conn())
    for u in users:
        u.pop("password", None)
    return jsonify(users)


@api_bp.route("/users", methods=["POST"])
@require_admin
def create_user():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = data.get("role", "user")

    if not name or not email or not password:
        return jsonify({"error": "name, email, and password are required"}), 400
    if role not in ("admin", "user"):
        return jsonify({"error": "role must be 'admin' or 'user'"}), 400

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        user_id = db.create_user(_conn(), name, email, pw_hash, role)
    except sqlite3.IntegrityError:
        return jsonify({"error": "Email already exists"}), 409

    return jsonify({"id": user_id}), 201


@api_bp.route("/users/<int:user_id>", methods=["PATCH"])
@require_admin
def update_user(user_id):
    data = request.get_json(force=True) or {}
    fields = {}

    if "name" in data:
        fields["name"] = (data["name"] or "").strip()
    if "email" in data:
        fields["email"] = (data["email"] or "").strip().lower()
    if "role" in data:
        if data["role"] not in ("admin", "user"):
            return jsonify({"error": "role must be 'admin' or 'user'"}), 400
        # Block demoting the last remaining admin
        target = db.get_user_by_id(_conn(), user_id)
        if (target and target["role"] == "admin"
                and data["role"] != "admin"
                and db.count_admins(_conn()) <= 1):
            return jsonify({"error": "Cannot demote the last admin"}), 409
        fields["role"] = data["role"]
    if data.get("password"):
        fields["password"] = bcrypt.hashpw(
            data["password"].encode(), bcrypt.gensalt()
        ).decode()

    try:
        db.update_user(_conn(), user_id, **fields)
    except sqlite3.IntegrityError:
        return jsonify({"error": "Email already exists"}), 409
    return jsonify({"ok": True})


@api_bp.route("/users/<int:user_id>", methods=["DELETE"])
@require_admin
def delete_user(user_id):
    if user_id == g.current_user["id"]:
        return jsonify({"error": "You cannot delete your own account"}), 409

    target = db.get_user_by_id(_conn(), user_id)
    if target and target["role"] == "admin" and db.count_admins(_conn()) <= 1:
        return jsonify({"error": "Cannot delete the last admin"}), 409

    db.delete_user(_conn(), user_id)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------

@api_bp.route("/cards", methods=["GET"])
@require_admin
def list_cards():
    return jsonify(db.list_cards(_conn()))


@api_bp.route("/cards", methods=["POST"])
@require_admin
def create_card():
    data = request.get_json(force=True) or {}
    uid = (data.get("uid") or "").strip().upper()
    label = (data.get("label") or "").strip() or None

    if not uid:
        return jsonify({"error": "uid is required"}), 400

    try:
        card_id = db.create_card(_conn(), uid, label)
    except sqlite3.IntegrityError:
        return jsonify({"error": "UID already registered"}), 409

    return jsonify({"id": card_id}), 201


@api_bp.route("/cards/<int:card_id>", methods=["PATCH"])
@require_admin
def update_card(card_id):
    data = request.get_json(force=True) or {}
    # user_id key present but None → unassign; absent → don't change
    user_id = data.get("user_id", ...)
    label = data.get("label", ...)

    card = db.get_card_by_id(_conn(), card_id)
    if card is None:
        return jsonify({"error": "Card not found"}), 404

    new_user_id = card["user_id"] if user_id is ... else user_id
    new_label = card["label"] if label is ... else (label or None)
    db.assign_card(_conn(), card_id, new_user_id, new_label)
    return jsonify({"ok": True})


@api_bp.route("/cards/<int:card_id>", methods=["DELETE"])
@require_admin
def delete_card(card_id):
    db.delete_card(_conn(), card_id)
    return jsonify({"ok": True})


@api_bp.route("/cards/capture", methods=["POST"])
@require_admin
def capture_card():
    """
    Long-poll tap-to-register endpoint.
    Puts the Pi reader into one-shot registration mode and blocks until a
    card is tapped (up to 30 s).  Returns {uid} on success, 408 on timeout.
    """
    handler = _handler()
    if handler is None:
        return jsonify({"error": "Card reader not available"}), 503

    timeout = 28.0
    captured: list[str] = []
    event = threading.Event()

    def on_capture(uid: str) -> None:
        captured.append(uid)
        event.set()

    handler.begin_registration(on_capture, timeout=timeout)
    fired = event.wait(timeout=timeout + 1.0)

    if not fired or not captured:
        handler.cancel_registration()
        return jsonify({"error": "Timeout — no card tapped"}), 408

    return jsonify({"uid": captured[0]})


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

@api_bp.route("/logs", methods=["GET"])
@require_admin
def list_logs():
    args = request.args
    user_id = args.get("user_id", type=int)
    from_dt = args.get("from") or None
    to_dt = args.get("to") or None
    page = max(1, args.get("page", 1, type=int))
    per_page = min(200, args.get("per_page", 20, type=int))

    rows, total = db.list_logs(_conn(), user_id=user_id, from_dt=from_dt,
                               to_dt=to_dt, page=page, per_page=per_page)
    return jsonify({"logs": rows, "total": total, "page": page, "per_page": per_page})


@api_bp.route("/logs/export.csv", methods=["GET"])
@require_admin
def export_logs_csv():
    args = request.args
    rows, _ = db.list_logs(
        _conn(),
        user_id=args.get("user_id", type=int),
        from_dt=args.get("from") or None,
        to_dt=args.get("to") or None,
        per_page=10_000,
    )

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=[
        "id", "timestamp", "action", "user_name", "card_uid", "card_label"
    ], extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=time_logs.csv"},
    )
