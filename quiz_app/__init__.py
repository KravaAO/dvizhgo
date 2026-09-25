"""Application infrastructure package."""

from flask import Flask

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
    return application
