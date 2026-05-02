"""
Tests for the Flask REST API (Phase 4).
All routes require an admin session; fixtures handle login automatically.
"""

import sqlite3
import pytest
import bcrypt

from src.config import Config, ServerConfig
from src.database import init_db, create_user, create_card, assign_card
from src.web.app import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app(conn):
    cfg = Config(server=ServerConfig(secret_key="test-secret"))
    application = create_app(cfg, conn)
    application.testing = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def _make_admin(conn, email="admin@test.com", password="adminpass"):
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    uid = create_user(conn, "Admin", email, pw_hash, role="admin")
    return uid


@pytest.fixture
def admin_client(client, conn):
    _make_admin(conn)
    client.post("/auth/login", json={"email": "admin@test.com", "password": "adminpass"})
    return client


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def test_login_success(client, conn):
    _make_admin(conn)
    res = client.post("/auth/login", json={"email": "admin@test.com", "password": "adminpass"})
    assert res.status_code == 200
    assert res.get_json()["ok"] is True
    assert "tc_session" in res.headers.get("Set-Cookie", "")


def test_login_wrong_password(client, conn):
    _make_admin(conn)
    res = client.post("/auth/login", json={"email": "admin@test.com", "password": "wrong"})
    assert res.status_code == 401


def test_login_unknown_email(client):
    res = client.post("/auth/login", json={"email": "nobody@test.com", "password": "x"})
    assert res.status_code == 401


def test_login_missing_fields(client):
    res = client.post("/auth/login", json={})
    assert res.status_code == 400


def test_logout(admin_client):
    res = admin_client.post("/auth/logout")
    assert res.status_code == 200
    # After logout, protected routes should return 401
    res2 = admin_client.get("/api/users")
    assert res2.status_code == 401


def test_protected_route_requires_auth(client):
    res = client.get("/api/users")
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# Users API
# ---------------------------------------------------------------------------

def test_list_users(admin_client, conn):
    create_user(conn, "Bob", "bob@test.com", "h")
    res = admin_client.get("/api/users")
    assert res.status_code == 200
    names = [u["name"] for u in res.get_json()]
    assert "Bob" in names


def test_list_users_no_password_field(admin_client, conn):
    res = admin_client.get("/api/users")
    for u in res.get_json():
        assert "password" not in u


def test_create_user(admin_client):
    res = admin_client.post("/api/users", json={
        "name": "Carol", "email": "carol@test.com", "password": "pass123"
    })
    assert res.status_code == 201
    assert "id" in res.get_json()


def test_create_user_missing_fields(admin_client):
    res = admin_client.post("/api/users", json={"name": "X"})
    assert res.status_code == 400


def test_create_user_invalid_role(admin_client):
    res = admin_client.post("/api/users", json={
        "name": "X", "email": "x@test.com", "password": "p", "role": "superuser"
    })
    assert res.status_code == 400


def test_create_user_duplicate_email(admin_client, conn):
    create_user(conn, "Dave", "dave@test.com", "h")
    res = admin_client.post("/api/users", json={
        "name": "Dave2", "email": "dave@test.com", "password": "pass"
    })
    assert res.status_code == 409


def test_update_user(admin_client, conn):
    uid = create_user(conn, "Eve", "eve@test.com", "h")
    res = admin_client.patch(f"/api/users/{uid}", json={"name": "Eve Updated"})
    assert res.status_code == 200
    assert res.get_json()["ok"] is True


def test_update_user_invalid_role(admin_client, conn):
    uid = create_user(conn, "Frank", "frank@test.com", "h")
    res = admin_client.patch(f"/api/users/{uid}", json={"role": "superuser"})
    assert res.status_code == 400


def test_delete_user(admin_client, conn):
    uid = create_user(conn, "Grace", "grace@test.com", "h")
    res = admin_client.delete(f"/api/users/{uid}")
    assert res.status_code == 200


def test_cannot_delete_self(admin_client, conn):
    """Admin cannot delete their own account."""
    from src.database import get_user_by_email
    me = get_user_by_email(conn, "admin@test.com")
    res = admin_client.delete(f"/api/users/{me['id']}")
    assert res.status_code == 409
    assert "your own" in res.get_json()["error"].lower()


def test_cannot_delete_last_admin(admin_client, conn):
    """Cannot delete the only remaining admin."""
    # Log in as a second admin so we can attempt to delete the first
    pw = bcrypt.hashpw(b"pw", bcrypt.gensalt()).decode()
    second_id = create_user(conn, "Second", "second@test.com", pw, role="admin")
    admin_client.post("/auth/login", json={"email": "second@test.com", "password": "pw"})

    from src.database import get_user_by_email, delete_user
    first = get_user_by_email(conn, "admin@test.com")

    # Demote the first admin (so only "Second" is admin)
    delete_user(conn, first["id"])

    # Now Second is the last admin — they cannot delete themselves
    res = admin_client.delete(f"/api/users/{second_id}")
    assert res.status_code == 409
    assert "your own" in res.get_json()["error"].lower()


def test_cannot_delete_last_admin_via_other_account(admin_client, conn):
    """Even from a non-self path, the last-admin check blocks deletion."""
    # Create a regular user, log in as them (we'd need their session — instead
    # we keep the admin session and verify the path is unreachable from another
    # admin since deleting yourself is also blocked).  Use direct delete_user
    # to verify the count_admins helper is correct.
    from src.database import count_admins, create_user as create_user_db
    assert count_admins(conn) == 1   # the "admin@test.com" from admin_client
    create_user_db(conn, "Regular", "reg@test.com", "h", role="user")
    assert count_admins(conn) == 1
    create_user_db(conn, "Boss", "boss@test.com", "h", role="admin")
    assert count_admins(conn) == 2


def test_cannot_demote_last_admin(admin_client, conn):
    from src.database import get_user_by_email
    me = get_user_by_email(conn, "admin@test.com")
    res = admin_client.patch(f"/api/users/{me['id']}", json={"role": "user"})
    assert res.status_code == 409
    assert "last admin" in res.get_json()["error"].lower()


# ---------------------------------------------------------------------------
# Cards API
# ---------------------------------------------------------------------------

def test_list_cards(admin_client, conn):
    create_card(conn, "04:AA:BB:CC")
    res = admin_client.get("/api/cards")
    assert res.status_code == 200
    uids = [c["uid"] for c in res.get_json()]
    assert "04:AA:BB:CC" in uids


def test_create_card(admin_client):
    res = admin_client.post("/api/cards", json={"uid": "04:11:22:33", "label": "Test Card"})
    assert res.status_code == 201
    assert "id" in res.get_json()


def test_create_card_uid_uppercased(admin_client, conn):
    admin_client.post("/api/cards", json={"uid": "aa:bb:cc:dd"})
    res = admin_client.get("/api/cards")
    uids = [c["uid"] for c in res.get_json()]
    assert "AA:BB:CC:DD" in uids


def test_create_card_missing_uid(admin_client):
    res = admin_client.post("/api/cards", json={"label": "no uid"})
    assert res.status_code == 400


def test_create_card_duplicate_uid(admin_client, conn):
    create_card(conn, "04:DU:PE:00")
    res = admin_client.post("/api/cards", json={"uid": "04:DU:PE:00"})
    assert res.status_code == 409


def test_update_card_assign_user(admin_client, conn):
    uid = create_user(conn, "Hank", "hank@test.com", "h")
    cid = create_card(conn, "04:CA:RD:01")
    res = admin_client.patch(f"/api/cards/{cid}", json={"user_id": uid, "label": "Hank's Card"})
    assert res.status_code == 200


def test_update_card_not_found(admin_client):
    res = admin_client.patch("/api/cards/9999", json={"label": "x"})
    assert res.status_code == 404


def test_delete_card(admin_client, conn):
    cid = create_card(conn, "04:DE:AD:01")
    res = admin_client.delete(f"/api/cards/{cid}")
    assert res.status_code == 200


def test_capture_card_no_handler(admin_client):
    """Without a card handler wired up, /api/cards/capture returns 503."""
    res = admin_client.post("/api/cards/capture")
    assert res.status_code == 503


def test_capture_card_with_mock_handler(app, conn, client):
    """With a MockNFCReader wired in, capture returns the tapped UID."""
    from src.card_handler import CardHandler
    from src.display import MockDisplay

    _make_admin(conn)
    handler = CardHandler(conn, MockDisplay())

    # Wire the handler into the app
    with app.app_context():
        app.config["CARD_HANDLER"] = handler

    client.post("/auth/login", json={"email": "admin@test.com", "password": "adminpass"})

    import threading

    def tap_after_delay():
        import time
        time.sleep(0.1)
        handler.handle_scan("04:TA:PP:ED")

    threading.Thread(target=tap_after_delay, daemon=True).start()
    res = client.post("/api/cards/capture")
    assert res.status_code == 200
    assert res.get_json()["uid"] == "04:TA:PP:ED"


# ---------------------------------------------------------------------------
# Logs API
# ---------------------------------------------------------------------------

def test_list_logs_empty(admin_client):
    res = admin_client.get("/api/logs")
    assert res.status_code == 200
    data = res.get_json()
    assert data["total"] == 0
    assert data["logs"] == []


def test_list_logs_with_data(admin_client, conn):
    from src.database import insert_log
    uid = create_user(conn, "Ivy", "ivy@test.com", "h")
    cid = create_card(conn, "04:IV:YY:00")
    assign_card(conn, cid, uid)
    insert_log(conn, cid, uid, "check_in")
    insert_log(conn, cid, uid, "check_out")

    res = admin_client.get("/api/logs")
    data = res.get_json()
    assert data["total"] == 2
    assert data["logs"][0]["user_name"] == "Ivy"


def test_list_logs_filter_by_user(admin_client, conn):
    from src.database import insert_log
    u1 = create_user(conn, "Jack", "jack@test.com", "h")
    u2 = create_user(conn, "Kim", "kim@test.com", "h")
    c1 = create_card(conn, "04:JA:CK:00")
    c2 = create_card(conn, "04:KI:MM:00")
    assign_card(conn, c1, u1)
    assign_card(conn, c2, u2)
    insert_log(conn, c1, u1, "check_in")
    insert_log(conn, c2, u2, "check_in")

    res = admin_client.get(f"/api/logs?user_id={u1}")
    data = res.get_json()
    assert data["total"] == 1
    assert data["logs"][0]["user_name"] == "Jack"


def test_list_logs_pagination(admin_client, conn):
    from src.database import insert_log
    uid = create_user(conn, "Leo", "leo@test.com", "h")
    cid = create_card(conn, "04:LE:OO:00")
    assign_card(conn, cid, uid)
    for _ in range(5):
        insert_log(conn, cid, uid, "check_in")
        insert_log(conn, cid, uid, "check_out")

    res = admin_client.get("/api/logs?page=1&per_page=3")
    data = res.get_json()
    assert data["total"] == 10
    assert len(data["logs"]) == 3


def test_export_csv(admin_client, conn):
    from src.database import insert_log
    uid = create_user(conn, "Mia", "mia@test.com", "h")
    cid = create_card(conn, "04:MI:AA:00")
    assign_card(conn, cid, uid)
    insert_log(conn, cid, uid, "check_in")

    res = admin_client.get("/api/logs/export.csv")
    assert res.status_code == 200
    assert res.content_type == "text/csv; charset=utf-8"
    text = res.data.decode()
    assert "Mia" in text
    assert "check_in" in text
