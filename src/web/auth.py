import secrets
import time
from datetime import datetime, timedelta
from functools import wraps

import bcrypt
from flask import (Blueprint, g, jsonify, make_response, redirect,
                   request, url_for, current_app)

from src import database as db

auth_bp = Blueprint("auth", __name__)

COOKIE_NAME = "tc_session"
SESSION_DAYS = 7

# ── Login rate-limiting (per remote IP) ──────────────────────────────
_LOGIN_WINDOW = 300        # seconds — 5-minute sliding window
_LOGIN_MAX = 10            # attempts per IP per window
_login_attempts: dict[str, list[float]] = {}

# ── Constant-time login dummy hash (lazy init) ───────────────────────
_DUMMY_HASH: bytes | None = None


def _conn():
    return current_app.config["DB_CONN"]


def _is_rate_limited(key: str) -> bool:
    """Return True if this IP has exceeded the failed-login limit."""
    now = time.monotonic()
    attempts = _login_attempts.get(key, [])
    attempts = [t for t in attempts if now - t < _LOGIN_WINDOW]
    _login_attempts[key] = attempts
    return len(attempts) >= _LOGIN_MAX


def _record_failure(key: str) -> None:
    _login_attempts.setdefault(key, []).append(time.monotonic())


def _clear_failures(key: str) -> None:
    _login_attempts.pop(key, None)


def _dummy_hash() -> bytes:
    """A bcrypt hash to compare against when no user exists, to prevent
    username enumeration via response timing."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = bcrypt.hashpw(b"x", bcrypt.gensalt())
    return _DUMMY_HASH


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
    ip = request.remote_addr or "unknown"
    if _is_rate_limited(ip):
        return jsonify({
            "error": "Too many failed login attempts. Try again in a few minutes."
        }), 429

    data = request.get_json(force=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "")

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    user = db.get_user_by_email(_conn(), email)

    # Always run a bcrypt comparison so the timing is the same for both
    # "no such user" and "wrong password" cases.
    if user is None:
        bcrypt.checkpw(password.encode(), _dummy_hash())
        _record_failure(ip)
        return jsonify({"error": "Invalid credentials"}), 401

    if not bcrypt.checkpw(password.encode(), user["password"].encode()):
        _record_failure(ip)
        return jsonify({"error": "Invalid credentials"}), 401

    # Successful login — clear any prior failures
    _clear_failures(ip)

    token = secrets.token_hex(32)
    expires = (datetime.utcnow() + timedelta(days=SESSION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    db.create_session(_conn(), token, user["id"], expires)
    db.delete_expired_sessions(_conn())

    resp = make_response(jsonify({"ok": True, "role": user["role"]}))
    resp.set_cookie(COOKIE_NAME, token, httponly=True, samesite="Strict",
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
