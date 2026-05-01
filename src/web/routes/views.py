from flask import Blueprint, g, render_template, redirect, url_for, request

from src import database as db
from src.web.auth import login_required, COOKIE_NAME

views_bp = Blueprint("views", __name__)


@views_bp.route("/login")
def login_page():
    return render_template("login.html")


@views_bp.route("/")
@login_required
def dashboard():
    from flask import current_app
    conn = current_app.config["DB_CONN"]
    recent_logs, _ = db.list_logs(conn, per_page=10)
    return render_template("dashboard.html", user=g.current_user, logs=recent_logs)


@views_bp.route("/logs")
@login_required
def logs_page():
    from flask import current_app
    conn = current_app.config["DB_CONN"]
    args = request.args
    page = max(1, args.get("page", 1, type=int))
    user_id = args.get("user_id", type=int)
    from_dt = args.get("from") or None
    to_dt = args.get("to") or None
    rows, total = db.list_logs(conn, user_id=user_id, from_dt=from_dt,
                               to_dt=to_dt, page=page, per_page=25)
    users = db.list_users(conn)
    return render_template("logs.html", user=g.current_user, logs=rows,
                           total=total, page=page, users=users,
                           filters={"user_id": user_id, "from": from_dt, "to": to_dt})


@views_bp.route("/cards")
@login_required
def cards_page():
    from flask import current_app
    conn = current_app.config["DB_CONN"]
    cards = db.list_cards(conn)
    users = db.list_users(conn)
    return render_template("cards.html", user=g.current_user,
                           cards=cards, users=users)


@views_bp.route("/users")
@login_required
def users_page():
    from flask import current_app
    conn = current_app.config["DB_CONN"]
    users = db.list_users(conn)
    for u in users:
        u.pop("password", None)
    return render_template("users.html", user=g.current_user, users=users)
