"""
Core business logic for processing an NFC card scan.

handle_scan(uid) is the single entry point called by the NFC polling loop.
It resolves the UID → card → user, toggles check-in/out, writes the log,
and drives the display + buzzer feedback.

Registration mode
-----------------
Call begin_registration(callback) to put the handler into a one-shot
"tap-to-register" mode.  The next card scan captures the UID and fires
the callback instead of doing a check-in/out.  This is how the admin
console registers new cards directly from the Pi reader.
"""

import logging
import threading
from typing import Callable, Optional

from src import database as db

logger = logging.getLogger(__name__)


class CardHandler:
    def __init__(self, conn, display) -> None:
        self._conn = conn
        self._display = display
        self._reg_callback: Optional[Callable[[str], None]] = None
        self._reg_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Registration mode
    # ------------------------------------------------------------------

    def begin_registration(self, callback: Callable[[str], None],
                           timeout: float = 30.0) -> None:
        """
        Enter tap-to-register mode for at most `timeout` seconds.
        The next card tap calls callback(uid) and exits registration mode.
        If no card is tapped within the timeout the mode cancels silently.
        """
        with self._reg_lock:
            self._reg_callback = callback

        def _expire():
            import time
            time.sleep(timeout)
            with self._reg_lock:
                if self._reg_callback is callback:
                    self._reg_callback = None
                    logger.debug("Registration mode timed out")

        t = threading.Thread(target=_expire, daemon=True)
        t.start()
        logger.info("Registration mode active (timeout=%.0fs)", timeout)

    def cancel_registration(self) -> None:
        with self._reg_lock:
            self._reg_callback = None

    # ------------------------------------------------------------------
    # Main scan handler
    # ------------------------------------------------------------------

    def handle_scan(self, uid: str) -> Optional[dict]:
        """
        Process one card tap.  Returns a result dict (useful for tests
        and the web layer) or None if handled as a registration capture.

        Result keys:
            action   'check_in' | 'check_out'
            user     user row dict
            card     card row dict
            log_id   int
        """
        # Registration mode takes priority
        with self._reg_lock:
            reg_cb = self._reg_callback
            if reg_cb is not None:
                self._reg_callback = None

        if reg_cb is not None:
            logger.info("Registration capture: %s", uid)
            self._display.show("Card captured", uid[:11], duration=2.0)
            self._display.buzz("check_in")
            reg_cb(uid)
            return None

        # Normal check-in / check-out flow
        card = db.get_card_by_uid(self._conn, uid)

        if card is None:
            logger.warning("Unknown card: %s", uid)
            self._display.show("Unknown card", uid[:11], duration=2.0)
            self._display.buzz("error")
            return None

        user_id = card.get("user_id")
        if user_id is None:
            logger.warning("Unassigned card: %s", uid)
            self._display.show("Unassigned card", card.get("label") or "", duration=2.0)
            self._display.buzz("error")
            return None

        user = db.get_user_by_id(self._conn, user_id)
        if user is None:
            logger.error("Card %s references missing user id %s", uid, user_id)
            self._display.show("Error", "User not found", duration=2.0)
            self._display.buzz("error")
            return None

        last_log = db.get_last_log_for_user(self._conn, user_id)
        action = "check_out" if (last_log and last_log["action"] == "check_in") else "check_in"

        log_id = db.insert_log(self._conn, card["id"], user_id, action)

        # Buzz immediately for tactile feedback, then show the confirmation screen
        self._display.buzz(action)
        self._display.show_scan_result(user["name"], action)

        logger.info("%s → %s (log_id=%d)", user["name"], action, log_id)
        return {"action": action, "user": dict(user), "card": dict(card), "log_id": log_id}
