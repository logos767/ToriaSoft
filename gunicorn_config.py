import logging

def post_worker_init(worker):
    """
    Hook de Gunicorn que se ejecuta después de que un worker ha sido inicializado.
    Aquí es donde iniciaremos la tarea en segundo plano de SocketIO.
    """
    # Importar la aplicación y socketio dentro del hook para asegurar que estén listos
    from app import app, socketio
    from app import update_exchange_rate_task

    # Configurar el logger para el worker
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info(f"Worker {worker.pid} inicializado. Iniciando tarea de actualización de tasa de cambio.")

    # Iniciar la tarea en segundo plano
    socketio.start_background_task(target=update_exchange_rate_task)

