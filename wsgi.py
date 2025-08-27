import eventlet
eventlet.monkey_patch()

from app import create_app

# Asignar el punto de entrada de Gunicorn ('app') directamente
# al atributo .socketio del resultado de create_app().
app = create_app().socketio