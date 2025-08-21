from app import create_app

app = create_app()

if __name__ == '__main__':
    # Use the socketio instance from the app context
    app.socketio.run(app, debug=True)