import eventlet
# Es crucial aplicar el monkey-patching al inicio para la compatibilidad con Gunicorn.
eventlet.monkey_patch()

# Importar solo la factory de la aplicación.
from app import create_app

# Crear la aplicación Flask. Dentro de esta función, la instancia de
# socketio es inicializada y adjuntada al objeto de la aplicación.
flask_app = create_app()

# El punto de entrada para Gunicorn ('app') debe ser la instancia de socketio.
# La extraemos del objeto de la aplicación Flask donde fue adjuntada.
app = flask_app.socketio
