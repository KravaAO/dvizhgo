"""Application infrastructure package."""

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import settings


def create_app() -> Flask:
    """Create the HTTP application with paths independent from the launcher."""
    application = Flask(
        "quiz_app",
        template_folder=str(settings.base_dir / "templates"),
        static_folder=str(settings.base_dir / "static"),
        static_url_path="/static",
    )
    application.secret_key = settings.secret_key
    if settings.is_production:
        # TLS terminates at the trusted KnowStack Nginx container.
        application.wsgi_app = ProxyFix(
            application.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1,
        )
        application.config.update(
            SESSION_COOKIE_SECURE=True,
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE="Lax",
            PREFERRED_URL_SCHEME="https",
        )
    return application
