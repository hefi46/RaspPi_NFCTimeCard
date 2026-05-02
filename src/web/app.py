import os
import socket
from datetime import datetime
from flask import Flask

from src.web.auth import auth_bp
from src.web.routes.api import api_bp
from src.web.routes.views import views_bp


def create_app(config, conn, card_handler=None):
    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    static_dir = os.path.join(os.path.dirname(__file__), "static")

    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
    app.secret_key = config.server.secret_key
    app.config["DB_CONN"] = conn
    app.config["CARD_HANDLER"] = card_handler

    reader_name = socket.gethostname() or "reader"
    hw_present = not config.hardware.mock and card_handler is not None

    @app.context_processor
    def _inject_shell():
        return {
            "reader_name": reader_name,
            "health": {
                "nfc":     hw_present,
                "display": hw_present,
                "buzzer":  hw_present,
            },
        }

    @app.template_filter("hhmmss")
    def _hhmmss(ts):
        if not ts:
            return ""
        try:
            return datetime.fromisoformat(str(ts)).strftime("%H:%M:%S")
        except ValueError:
            return str(ts)[-8:]

    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(views_bp)

    return app
