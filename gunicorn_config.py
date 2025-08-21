
def post_worker_init(worker):
    """
    Hook de Gunicorn que se ejecuta después de que un worker ha sido inicializado.
    Aquí es donde iniciaremos la tarea en segundo plano de SocketIO.
    """
    # Usar el logger de Gunicorn es la mejor práctica.
    worker.log.info(f"Worker {worker.pid} inicializado. Iniciando tarea de actualización de tasa de cambio.")
    
    # Solo necesitamos importar los objetos que vamos a usar.
    from app import socketio, update_exchange_rate_task
    
    # Iniciar la tarea en segundo plano
    socketio.start_background_task(target=update_exchange_rate_task)
    worker.log.info(f"Tarea en segundo plano iniciada para el worker {worker.pid}.")
