"""Application composition root.

Only infrastructure is assembled here. HTTP routes and domain rules are
registered by dedicated modules, keeping deployment entry points side-effect
free apart from creating the WSGI/Socket.IO application.
"""

import logging

from flask_socketio import SocketIO

from . import create_app
from .config import settings


app = create_app()
app.logger.setLevel(logging.INFO)
socketio = SocketIO(
    app,
    async_mode="threading",
    message_queue=settings.socketio_message_queue,
)

# Import after extensions exist: route decorators attach to this application.
from . import routes as _routes  # noqa: E402, F401


def init_db():
    """Initialize persistent storage for the configured deployment."""
    _routes.init_db()
