import os
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

    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(views_bp)

    return app
