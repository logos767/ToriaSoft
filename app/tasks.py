import logging
from flask import current_app
from .extensions import db, socketio
from .models import ExchangeRate
from .utils import obtener_tasa_p2p_binance

logger = logging.getLogger(__name__)

def update_exchange_rate_task():
    """
    Background task to update the exchange rate every hour.
    Uses socketio.sleep to be compatible with eventlet.
    """
    logger.info("Background exchange rate task is ready to start.")
    socketio.sleep(10) # Initial delay to allow the app to fully start
    while True:
        try:
            with current_app.app_context():
                logger.info("Executing exchange rate update...")
                new_rate = obtener_tasa_p2p_binance()
                if new_rate:
                    rate_entry = ExchangeRate.query.first()
                    if not rate_entry:
                        rate_entry = ExchangeRate(rate=new_rate)
                        db.session.add(rate_entry)
                    else:
                        rate_entry.rate = new_rate
                    db.session.commit()
                    logger.info(f"Exchange rate updated to: {new_rate}")
        except Exception as e:
            logger.error(f"Error in exchange rate task: {e}", exc_info=True)
            with current_app.app_context():
                db.session.rollback()
        socketio.sleep(3600) # Wait 1 hour