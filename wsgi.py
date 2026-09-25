"""Production entry point used by Gunicorn and container deployments."""

from app import app, init_db

init_db()
