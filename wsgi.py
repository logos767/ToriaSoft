import eventlet
# Explicitly monkey-patch before any other imports.
# This is necessary to prevent threading issues with libraries like SQLAlchemy
# when using eventlet with Gunicorn, as evidenced by runtime errors.
# Gunicorn with the eventlet worker is supposed to handle this, but in some
# deployment environments, explicit patching is required to ensure it happens
# before other modules are imported.
eventlet.monkey_patch()

# This is the WSGI entry point for production servers like Gunicorn.
#
# The `create_app` factory is expected to initialize all extensions, including SocketIO.
#
# Example Gunicorn command for production:
# gunicorn --worker-class eventlet -w 1 wsgi:app

from app import create_app

app = create_app()
