import eventlet
eventlet.monkey_patch()

from app import create_app, socketio

app = create_app()

if __name__ == '__main__':
    # This is for local development.
    # The 'app' object is used by Gunicorn in production.
    socketio.run(app, debug=True)