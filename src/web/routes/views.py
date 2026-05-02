from flask import Blueprint, current_app, g, render_template, request

from src import database as db
from src.web.auth import login_required

views_bp = Blueprint("views", __name__)

PER_PAGE = 25


def _conn():
    return current_app.config["DB_CONN"]


@views_bp.route("/login")
def login_page():
    return render_template("login.html")


@views_bp.route("/")
@login_required
def dashboard():
    conn = _conn()
    recent_logs, total_logs = db.list_logs(conn, per_page=10)
    checked_in = db.count_checked_in(conn)
    return render_template("dashboard.html", user=g.current_user,
                           logs=recent_logs, total_logs=total_logs,
                           checked_in=checked_in)


@views_bp.route("/logs")
@login_required
def logs_page():
    conn = _conn()
    args = request.args
    page = max(1, args.get("page", 1, type=int))
    user_id = args.get("user_id", type=int)
    from_dt = args.get("from") or None
    to_dt = args.get("to") or None
    rows, total = db.list_logs(conn, user_id=user_id, from_dt=from_dt,
                               to_dt=to_dt, page=page, per_page=PER_PAGE)
    users = db.list_users(conn)
    for u in users:
        u.pop("password", None)
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    return render_template("logs.html", user=g.current_user, logs=rows,
                           total=total, page=page, pages=pages, users=users,
                           filters={"user_id": user_id, "from": from_dt, "to": to_dt})


@views_bp.route("/cards")
@login_required
def cards_page():
    conn = _conn()
    cards = db.list_cards(conn)
    users = db.list_users(conn)
    for u in users:
        u.pop("password", None)
    return render_template("cards.html", user=g.current_user,
                           cards=cards, users=users)


@views_bp.route("/users")
@login_required
def users_page():
    conn = _conn()
    users = db.list_users(conn)
    for u in users:
        u.pop("password", None)
    return render_template("users.html", user=g.current_user, users=users)
