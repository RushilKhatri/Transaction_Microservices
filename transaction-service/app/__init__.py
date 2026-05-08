"""
app/__init__.py — Transaction Service
Flask application factory.
Initialises SQLAlchemy, Flask-JWT-Extended, and structured JSON logging.
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_cors import CORS

db = SQLAlchemy()
jwt = JWTManager()


def create_app(config_object=None):
    app = Flask(__name__)
    CORS(app)

    # ── Configuration ─────────────────────────────────────────────────────────
    if config_object is None:
        from config import Config  # noqa: PLC0415
        config_object = Config

    app.config.from_object(config_object)

    # ── Extensions ────────────────────────────────────────────────────────────
    db.init_app(app)
    jwt.init_app(app)

    # ── Structured logging ────────────────────────────────────────────────────
    from app.utils import setup_logger  # noqa: PLC0415
    logger = setup_logger("transaction-service")

    # ── Blueprints ────────────────────────────────────────────────────────────
    from app.routes import api  # noqa: PLC0415
    app.register_blueprint(api)

    # ── DB tables ─────────────────────────────────────────────────────────────
    with app.app_context():
        db.create_all()
        logger.info("Database tables ensured", extra={"event": "startup"})

    return app
