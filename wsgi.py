# This is the WSGI entry point for production servers like Gunicorn.
#
# It does not call eventlet.monkey_patch(), because when using Gunicorn with
# the eventlet worker, Gunicorn itself is responsible for monkey-patching.
# The `create_app` factory is expected to initialize all extensions, including SocketIO.
#
# Example Gunicorn command for production:
# gunicorn --worker-class eventlet -w 1 wsgi:app

from app import create_app

app = create_app()

