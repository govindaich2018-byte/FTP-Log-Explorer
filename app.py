"""FTP Log Explorer – Flask application entry point."""

import os
import secrets

from flask import Flask

from routes import bp


def create_app() -> Flask:
    app = Flask(__name__)

    # Secret key for session signing – generated fresh each run so credentials
    # are invalidated when the server restarts (never stored on disk).
    app.secret_key = secrets.token_hex(32)

    # Sessions are cookie-based and never written to disk.
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    app.register_blueprint(bp)
    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="127.0.0.1", port=5000, debug=False)
