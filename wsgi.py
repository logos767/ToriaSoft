import eventlet
# Es crucial aplicar el monkey-patching al inicio para la compatibilidad con Gunicorn.
eventlet.monkey_patch()

# Importar la factory de la app y la instancia de socketio
from app import create_app, socketio

# Crear la aplicación Flask usando la factory.
# La inicialización de socketio con la app ocurre dentro de esta función.
create_app()

# El punto de entrada para Gunicorn debe ser la instancia de socketio.
# Esta instancia ya conoce la aplicación Flask y la gestiona.
app = socketio