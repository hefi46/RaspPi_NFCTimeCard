import secrets
from datetime import datetime, timedelta
from functools import wraps

import bcrypt
from flask import (Blueprint, g, jsonify, make_response, redirect,
                   request, url_for, current_app)

from src import database as db

auth_bp = Blueprint("auth", __name__)

COOKIE_NAME = "tc_session"
SESSION_DAYS = 7


def _conn():
    return current_app.config["DB_CONN"]


def require_admin(f):
    """Protects API routes — returns JSON 401/403 on failure."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get(COOKIE_NAME)
        session = db.get_session(_conn(), token) if token else None
        if not session:
            return jsonify({"error": "Unauthorized"}), 401
        user = db.get_user_by_id(_conn(), session["user_id"])
        if not user or user["role"] != "admin":
            return jsonify({"error": "Forbidden"}), 403
        g.current_user = user
        return f(*args, **kwargs)
    return decorated


def login_required(f):
    """Protects HTML view routes — redirects to /login on failure."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get(COOKIE_NAME)
        session = db.get_session(_conn(), token) if token else None
        if not session:
            return redirect(url_for("views.login_page"))
        user = db.get_user_by_id(_conn(), session["user_id"])
        if not user or user["role"] != "admin":
            return redirect(url_for("views.login_page"))
        g.current_user = user
        return f(*args, **kwargs)
    return decorated


@auth_bp.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json(force=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "")

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    user = db.get_user_by_email(_conn(), email)
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    if not bcrypt.checkpw(password.encode(), user["password"].encode()):
        return jsonify({"error": "Invalid credentials"}), 401

    token = secrets.token_hex(32)
    expires = (datetime.utcnow() + timedelta(days=SESSION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    db.create_session(_conn(), token, user["id"], expires)
    db.delete_expired_sessions(_conn())

    resp = make_response(jsonify({"ok": True, "role": user["role"]}))
    resp.set_cookie(COOKIE_NAME, token, httponly=True, samesite="Lax",
                    max_age=SESSION_DAYS * 86400)
    return resp


@auth_bp.route("/auth/logout", methods=["POST"])
def logout():
    token = request.cookies.get(COOKIE_NAME)
    if token:
        db.delete_session(_conn(), token)
    resp = make_response(jsonify({"ok": True}))
    resp.delete_cookie(COOKIE_NAME)
    return resp
