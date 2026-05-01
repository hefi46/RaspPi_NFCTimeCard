import pytest
from src.database import (
    create_user, get_user_by_id, get_user_by_email, list_users,
    update_user, delete_user,
    create_card, get_card_by_uid, get_card_by_id, list_cards,
    assign_card, delete_card,
    insert_log, get_last_log_for_user, list_logs,
    create_session, get_session, delete_session, delete_expired_sessions,
)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def test_create_and_fetch_user(conn):
    uid = create_user(conn, "Alice", "alice@example.com", "hashed", role="admin")
    user = get_user_by_id(conn, uid)
    assert user["name"] == "Alice"
    assert user["email"] == "alice@example.com"
    assert user["role"] == "admin"


def test_get_user_by_email(conn):
    create_user(conn, "Bob", "bob@example.com", "hashed")
    user = get_user_by_email(conn, "bob@example.com")
    assert user is not None
    assert user["name"] == "Bob"


def test_get_user_by_email_missing(conn):
    assert get_user_by_email(conn, "nobody@example.com") is None


def test_list_users(conn):
    create_user(conn, "Charlie", "charlie@example.com", "h")
    create_user(conn, "Dave", "dave@example.com", "h")
    users = list_users(conn)
    names = [u["name"] for u in users]
    assert "Charlie" in names
    assert "Dave" in names


def test_update_user(conn):
    uid = create_user(conn, "Eve", "eve@example.com", "h")
    update_user(conn, uid, name="Eve Updated", role="admin")
    user = get_user_by_id(conn, uid)
    assert user["name"] == "Eve Updated"
    assert user["role"] == "admin"


def test_update_user_ignores_unknown_fields(conn):
    uid = create_user(conn, "Frank", "frank@example.com", "h")
    update_user(conn, uid, nonexistent="value")
    assert get_user_by_id(conn, uid)["name"] == "Frank"


def test_delete_user(conn):
    uid = create_user(conn, "Grace", "grace@example.com", "h")
    delete_user(conn, uid)
    assert get_user_by_id(conn, uid) is None


def test_duplicate_email_raises(conn):
    create_user(conn, "Hank", "hank@example.com", "h")
    with pytest.raises(Exception):
        create_user(conn, "Hank2", "hank@example.com", "h")


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------

def test_create_and_fetch_card(conn):
    cid = create_card(conn, "04:AB:CD:12", label="Card A")
    card = get_card_by_id(conn, cid)
    assert card["uid"] == "04:AB:CD:12"
    assert card["label"] == "Card A"
    assert card["user_id"] is None


def test_get_card_by_uid(conn):
    create_card(conn, "AA:BB:CC:DD")
    card = get_card_by_uid(conn, "AA:BB:CC:DD")
    assert card is not None


def test_get_card_by_uid_missing(conn):
    assert get_card_by_uid(conn, "00:00:00:00") is None


def test_assign_card(conn):
    uid = create_user(conn, "Ivy", "ivy@example.com", "h")
    cid = create_card(conn, "11:22:33:44")
    assign_card(conn, cid, uid)
    card = get_card_by_id(conn, cid)
    assert card["user_id"] == uid
    assert card["assigned_at"] is not None


def test_assign_card_with_label(conn):
    uid = create_user(conn, "Jack", "jack@example.com", "h")
    cid = create_card(conn, "55:66:77:88")
    assign_card(conn, cid, uid, label="Jack's Card")
    card = get_card_by_id(conn, cid)
    assert card["label"] == "Jack's Card"


def test_list_cards_includes_user_name(conn):
    uid = create_user(conn, "Kim", "kim@example.com", "h")
    cid = create_card(conn, "99:AA:BB:CC")
    assign_card(conn, cid, uid)
    cards = list_cards(conn)
    matched = next(c for c in cards if c["id"] == cid)
    assert matched["user_name"] == "Kim"


def test_delete_card(conn):
    cid = create_card(conn, "DE:AD:BE:EF")
    delete_card(conn, cid)
    assert get_card_by_id(conn, cid) is None


# ---------------------------------------------------------------------------
# Time logs
# ---------------------------------------------------------------------------

def test_insert_and_fetch_log(conn):
    uid = create_user(conn, "Leo", "leo@example.com", "h")
    cid = create_card(conn, "01:02:03:04")
    assign_card(conn, cid, uid)

    log_id = insert_log(conn, cid, uid, "check_in")
    log = get_last_log_for_user(conn, uid)
    assert log is not None
    assert log["id"] == log_id
    assert log["action"] == "check_in"


def test_last_log_returns_most_recent(conn):
    uid = create_user(conn, "Mia", "mia@example.com", "h")
    cid = create_card(conn, "05:06:07:08")
    assign_card(conn, cid, uid)

    insert_log(conn, cid, uid, "check_in")
    insert_log(conn, cid, uid, "check_out")
    log = get_last_log_for_user(conn, uid)
    assert log["action"] == "check_out"


def test_last_log_none_when_no_logs(conn):
    uid = create_user(conn, "Ned", "ned@example.com", "h")
    assert get_last_log_for_user(conn, uid) is None


def test_list_logs_basic(conn):
    uid = create_user(conn, "Olivia", "olivia@example.com", "h")
    cid = create_card(conn, "09:0A:0B:0C")
    assign_card(conn, cid, uid)
    insert_log(conn, cid, uid, "check_in")
    insert_log(conn, cid, uid, "check_out")

    rows, total = list_logs(conn)
    assert total == 2
    assert len(rows) == 2


def test_list_logs_filter_by_user(conn):
    u1 = create_user(conn, "Pat", "pat@example.com", "h")
    u2 = create_user(conn, "Quinn", "quinn@example.com", "h")
    c1 = create_card(conn, "10:11:12:13")
    c2 = create_card(conn, "14:15:16:17")
    assign_card(conn, c1, u1)
    assign_card(conn, c2, u2)
    insert_log(conn, c1, u1, "check_in")
    insert_log(conn, c2, u2, "check_in")

    rows, total = list_logs(conn, user_id=u1)
    assert total == 1
    assert rows[0]["user_name"] == "Pat"


def test_list_logs_pagination(conn):
    uid = create_user(conn, "Rosa", "rosa@example.com", "h")
    cid = create_card(conn, "18:19:1A:1B")
    assign_card(conn, cid, uid)
    for action in ["check_in", "check_out"] * 5:
        insert_log(conn, cid, uid, action)

    rows, total = list_logs(conn, page=1, per_page=3)
    assert total == 10
    assert len(rows) == 3


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def test_create_and_get_session(conn):
    uid = create_user(conn, "Sam", "sam@example.com", "h")
    create_session(conn, "tok123", uid, "2099-01-01 00:00:00")
    sess = get_session(conn, "tok123")
    assert sess is not None
    assert sess["user_id"] == uid


def test_get_expired_session_returns_none(conn):
    uid = create_user(conn, "Tara", "tara@example.com", "h")
    create_session(conn, "oldtok", uid, "2000-01-01 00:00:00")
    assert get_session(conn, "oldtok") is None


def test_delete_session(conn):
    uid = create_user(conn, "Uma", "uma@example.com", "h")
    create_session(conn, "delme", uid, "2099-01-01 00:00:00")
    delete_session(conn, "delme")
    assert get_session(conn, "delme") is None


def test_delete_expired_sessions(conn):
    uid = create_user(conn, "Vera", "vera@example.com", "h")
    create_session(conn, "active", uid, "2099-01-01 00:00:00")
    create_session(conn, "expired", uid, "2000-01-01 00:00:00")
    delete_expired_sessions(conn)
    assert get_session(conn, "active") is not None
    # expired session is gone (direct lookup bypassing date filter)
    row = conn.execute("SELECT * FROM sessions WHERE token = 'expired'").fetchone()
    assert row is None
