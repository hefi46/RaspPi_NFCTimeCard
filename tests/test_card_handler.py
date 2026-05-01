import threading
import pytest
from src.card_handler import CardHandler
from src.display import MockDisplay
from src import database as db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def display():
    return MockDisplay()


@pytest.fixture
def handler(conn, display):
    return CardHandler(conn, display)


@pytest.fixture
def seeded(conn):
    """Return (user, card) dicts for a fully set-up user+card pair."""
    uid = db.create_user(conn, "Alice", "alice@example.com", "hashed")
    cid = db.create_card(conn, "04:AA:BB:CC", label="Alice Card")
    db.assign_card(conn, cid, uid)
    user = db.get_user_by_id(conn, uid)
    card = db.get_card_by_id(conn, cid)
    return user, card


# ---------------------------------------------------------------------------
# Normal check-in / check-out flow
# ---------------------------------------------------------------------------

def test_first_scan_is_check_in(conn, handler, seeded):
    user, card = seeded
    result = handler.handle_scan(card["uid"])
    assert result is not None
    assert result["action"] == "check_in"
    assert result["user"]["id"] == user["id"]
    assert result["log_id"] is not None


def test_second_scan_is_check_out(conn, handler, seeded):
    _, card = seeded
    handler.handle_scan(card["uid"])
    result = handler.handle_scan(card["uid"])
    assert result["action"] == "check_out"


def test_toggle_sequence(conn, handler, seeded):
    _, card = seeded
    actions = [handler.handle_scan(card["uid"])["action"] for _ in range(4)]
    assert actions == ["check_in", "check_out", "check_in", "check_out"]


def test_log_written_to_db(conn, handler, seeded):
    _, card = seeded
    handler.handle_scan(card["uid"])
    rows, total = db.list_logs(conn)
    assert total == 1
    assert rows[0]["action"] == "check_in"


def test_display_called_on_success(conn, seeded, display, monkeypatch):
    _, card = seeded
    calls = []
    monkeypatch.setattr(display, "show_scan_result", lambda name, action: calls.append((name, action)))
    h = CardHandler(conn, display)
    h.handle_scan(card["uid"])
    assert len(calls) == 1
    assert calls[0] == ("Alice", "check_in")


def test_buzz_called_on_success(conn, seeded, display, monkeypatch):
    _, card = seeded
    buzzed = []
    monkeypatch.setattr(display, "buzz", lambda p: buzzed.append(p))
    h = CardHandler(conn, display)
    h.handle_scan(card["uid"])
    assert buzzed == ["check_in"]


def test_buzz_fires_before_display(conn, seeded, display, monkeypatch):
    """buzz() must be called before show_scan_result() for immediate feedback."""
    _, card = seeded
    order = []
    monkeypatch.setattr(display, "buzz", lambda p: order.append("buzz"))
    monkeypatch.setattr(display, "show_scan_result", lambda n, a: order.append("show"))
    h = CardHandler(conn, display)
    h.handle_scan(card["uid"])
    assert order == ["buzz", "show"]


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_unknown_uid_returns_none(conn, handler):
    result = handler.handle_scan("00:00:00:00")
    assert result is None


def test_unknown_uid_error_buzz(conn, display, monkeypatch):
    buzzed = []
    monkeypatch.setattr(display, "buzz", lambda p: buzzed.append(p))
    h = CardHandler(conn, display)
    h.handle_scan("FF:FF:FF:FF")
    assert buzzed == ["error"]


def test_unassigned_card_returns_none(conn, handler):
    db.create_card(conn, "01:02:03:04")
    result = handler.handle_scan("01:02:03:04")
    assert result is None


def test_unassigned_card_error_buzz(conn, display, monkeypatch):
    db.create_card(conn, "05:06:07:08")
    buzzed = []
    monkeypatch.setattr(display, "buzz", lambda p: buzzed.append(p))
    h = CardHandler(conn, display)
    h.handle_scan("05:06:07:08")
    assert buzzed == ["error"]


# ---------------------------------------------------------------------------
# Registration mode
# ---------------------------------------------------------------------------

def test_registration_captures_uid(conn, handler):
    captured = []
    handler.begin_registration(callback=captured.append)
    result = handler.handle_scan("04:NEW:UID:01")
    assert result is None                    # not a check-in/out
    assert captured == ["04:NEW:UID:01"]


def test_registration_only_fires_once(conn, handler):
    captured = []
    handler.begin_registration(callback=captured.append)
    handler.handle_scan("04:NEW:UID:01")
    # second tap should fall through to normal (unknown card) flow
    result = handler.handle_scan("04:NEW:UID:01")
    assert result is None        # unknown card, but NOT a registration capture
    assert len(captured) == 1    # callback only called once


def test_registration_can_be_cancelled(conn, handler):
    captured = []
    handler.begin_registration(callback=captured.append)
    handler.cancel_registration()
    handler.handle_scan("04:NEW:UID:02")
    assert captured == []


def test_registration_capture_shown_on_display(conn, display, monkeypatch):
    shown = []
    monkeypatch.setattr(display, "show", lambda *a, **kw: shown.append(a))
    h = CardHandler(conn, display)
    h.begin_registration(callback=lambda uid: None)
    h.handle_scan("04:CA:PT:UR")
    assert shown and "captured" in shown[0][0].lower()


def test_registration_timeout_cancels(conn, handler):
    """Registration mode with a very short timeout expires without crashing."""
    captured = []
    handler.begin_registration(callback=captured.append, timeout=0.05)
    import time
    time.sleep(0.1)
    # After timeout, a scan should NOT fire the callback
    handler.handle_scan("04:AF:TE:RT")
    assert captured == []
