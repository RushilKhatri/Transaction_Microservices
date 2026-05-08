"""
app/__init__.py — Fraud Detection Service
Flask application factory (no database — stateless service).
"""

from flask import Flask
from flask_jwt_extended import JWTManager
from flask_cors import CORS

jwt = JWTManager()


def create_app(config_object=None):
    app = Flask(__name__)
    CORS(app)

    if config_object is None:
        from config import Config  # noqa: PLC0415
        config_object = Config

    app.config.from_object(config_object)

    jwt.init_app(app)

    from app.utils import setup_logger  # noqa: PLC0415
    logger = setup_logger("fraud-detection-service")

    from app.routes import api  # noqa: PLC0415
    app.register_blueprint(api)

    logger.info("Fraud detection service started", extra={"event": "startup"})
    return app
