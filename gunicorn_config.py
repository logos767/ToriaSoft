def when_ready(server):
    """
    Hook de Gunicorn que se ejecuta cuando el servidor maestro está listo.
    Aquí es donde iniciaremos la tarea en segundo plano de SocketIO,
    asegurando que se ejecute una sola vez en el proceso principal.
    """
    server.log.info("Server master is ready. Starting background task.")
    
    # Importar aquí para asegurar que la app esté completamente cargada.
    from app import socketio, update_exchange_rate_task

    # Iniciar la tarea en segundo plano
    socketio.start_background_task(target=update_exchange_rate_task)
    server.log.info("Background task started in master process.")