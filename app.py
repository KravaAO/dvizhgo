"""Compatibility entry point for local Flask and production WSGI servers."""

from quiz_app.bootstrap import app, init_db, socketio


if __name__ == "__main__":
    init_db()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
