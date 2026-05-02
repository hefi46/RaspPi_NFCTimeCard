"""
Application entry point.

Starts three things in order:
  1. SQLite DB (init schema if first run)
  2. Display idle loop (daemon thread)
  3. NFC reader polling loop (daemon thread)
  4. Flask web server (main thread — blocks until Ctrl-C)

In mock mode (config.hardware.mock = true) the hardware classes are
replaced with stdout stubs and a /dev tap-simulator route is mounted.
"""

import logging
import os
import threading

from src.card_handler import CardHandler
from src.config import load_config
from src.database import connect, init_db
from src.display import make_display
from src.nfc_reader import make_reader
from src.web.app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    config = load_config()

    # ── Database ──────────────────────────────────────────────────────
    db_dir = os.path.dirname(config.database.path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = connect(config.database.path)
    init_db(conn)
    logger.info("Database ready: %s", config.database.path)

    # ── Display ───────────────────────────────────────────────────────
    display = make_display(config)
    display.start_idle()
    logger.info("Display started (%s)", "mock" if config.hardware.mock else "ILI9341")

    # ── Card handler ──────────────────────────────────────────────────
    handler = CardHandler(conn, display)

    # ── NFC reader ────────────────────────────────────────────────────
    reader = make_reader(config)
    nfc_thread = threading.Thread(
        target=reader.start,
        args=(handler.handle_scan,),
        daemon=True,
        name="nfc-reader",
    )
    nfc_thread.start()
    logger.info("NFC reader started (%s)", "mock" if config.hardware.mock else "PN532")

    # ── Flask app ─────────────────────────────────────────────────────
    app = create_app(config, conn, card_handler=handler)

    if config.hardware.mock:
        from src.web.routes.dev import dev_bp
        app.register_blueprint(dev_bp)
        app.config["NFC_READER"] = reader
        logger.info("Dev tap simulator mounted at /dev")

    logger.info(
        "Web server starting on http://%s:%d",
        config.server.host, config.server.port,
    )

    # Werkzeug installs its own signal handlers when app.run() starts, so
    # rely on try/finally for cleanup rather than a custom SIGINT handler.
    try:
        app.run(
            host=config.server.host,
            port=config.server.port,
            debug=False,
            use_reloader=False,   # reloader forks and breaks the hardware threads
            threaded=True,
        )
    finally:
        logger.info("Shutting down…")
        reader.stop()
        display.cleanup()


if __name__ == "__main__":
    main()
