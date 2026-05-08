"""
app/__init__.py — Notification Service
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

    if config_object is None:
        from config import Config  # noqa: PLC0415
        config_object = Config

    app.config.from_object(config_object)

    db.init_app(app)
    jwt.init_app(app)

    from app.utils import setup_logger  # noqa: PLC0415
    logger = setup_logger("notification-service")

    from app.routes import api  # noqa: PLC0415
    app.register_blueprint(api)

    with app.app_context():
        db.create_all()
        logger.info("Database tables ensured", extra={"event": "startup"})

    return app
