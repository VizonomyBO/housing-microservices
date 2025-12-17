"""
Account Service Application Factory
"""

# CRITICAL: Initialize db FIRST before any other imports to avoid circular import issues
# Models use db.Model, so we need db to be available even in FastAPI mode
# Flask-SQLAlchemy requires a Flask app to initialize, so we create a minimal one
try:
    import os

    from flask import Flask
    from flask_sqlalchemy import SQLAlchemy

    # Create a minimal Flask app just to initialize SQLAlchemy (legacy compatibility)
    _minimal_app = Flask(__name__)
    _minimal_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    _minimal_app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "AUTH_DATABASE_URL", os.getenv("DATABASE_URL", "sqlite:///:memory:")
    )
    db = SQLAlchemy()
    db.init_app(_minimal_app)
    _DB_AVAILABLE = True
except ImportError:
    _DB_AVAILABLE = False
    db = None  # type: ignore[assignment]
    _minimal_app = None  # type: ignore[assignment]

# Import Config after db is initialized to avoid circular imports
from app.config import Config

# Conditional Flask imports for full Flask app support
_FLASK_AVAILABLE = _DB_AVAILABLE
try:
    from flask_cors import CORS

    _CORS_AVAILABLE = True
except ImportError:
    # Flask extensions not available - this is fine for FastAPI mode
    _CORS_AVAILABLE = False


def create_app(config_class=Config):
    """Application factory pattern (Flask) - only works when Flask is available"""
    if not _FLASK_AVAILABLE:
        raise RuntimeError(
            "Flask is not available. This function requires Flask to be installed. "
            "For FastAPI, use app.main:app instead."
        )

    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    if db is not None:
        db.init_app(app)
    if _CORS_AVAILABLE:
        CORS(
            app,
            resources={
                r"/*": {
                    "origins": app.config.get("CORS_ORIGINS", ["*"]),
                    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                    "allow_headers": ["Content-Type", "Authorization"],
                    "expose_headers": ["Content-Type", "Authorization"],
                    "supports_credentials": True,
                }
            },
        )

    # Register blueprints
    from app.api.auth import auth_bp  # type: ignore[attr-defined]
    from app.api.system import system_bp  # type: ignore[attr-defined]

    app.register_blueprint(auth_bp, url_prefix="/v1/auth")
    app.register_blueprint(system_bp)

    # Add security headers
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        return response

    return app
