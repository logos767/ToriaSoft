import eventlet
eventlet.monkey_patch()

from app import create_app, socketio

app = create_app()

if __name__ == '__main__':
    # This file is intended for local development only.
    # For production, use a WSGI server like Gunicorn pointing to wsgi.py.
    socketio.run(app, debug=True)