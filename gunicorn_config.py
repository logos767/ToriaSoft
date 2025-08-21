
def post_worker_init(worker):
    """
    Hook de Gunicorn que se ejecuta después de que un worker ha sido inicializado.
    Aquí es donde iniciaremos la tarea en segundo plano de SocketIO.
    """
    # Use Gunicorn's logger for best practice.
    worker.log.info(f"Worker {worker.pid} initialized. Starting background task.")
    
    # We only need to import the objects we are going to use.
    from app import socketio, update_exchange_rate_task

    # Iniciar la tarea en segundo plano
    socketio.start_background_task(target=update_exchange_rate_task)
    worker.log.info(f"Background task started for worker {worker.pid}.")
