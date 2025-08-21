import eventlet
eventlet.monkey_patch()

from app import create_app, socketio

app = create_app()

if __name__ == '__main__':
    # Use the socketio instance from the app context
    app.socketio.run(app, debug=True)