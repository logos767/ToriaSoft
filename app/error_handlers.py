from flask import flash, redirect, request, url_for, current_app, render_template, session
from sqlalchemy.exc import OperationalError
from requests.exceptions import ConnectionError # type: ignore
from werkzeug.exceptions import InternalServerError, NotFound, Forbidden
from .extensions import db
from .models import ExchangeRate, CompanyInfo

def get_cached_exchange_rate(currency='USD'):
    """
    Obtiene la última tasa de cambio guardada en la base de datos para una moneda específica.
    """
    try:
        cached_rate = ExchangeRate.query.filter_by(currency=currency).order_by(ExchangeRate.date_updated.desc()).first()
        if cached_rate:
            return cached_rate.rate
    except Exception as e:
        current_app.logger.error(f"Error al obtener la tasa de cambio '{currency}' de la base de datos: {e}")
        db.session.rollback()
    
    current_app.logger.warning(f"No se encontró una tasa de cambio para '{currency}' en la base de datos.")
    return None

def register_error_handlers(app):
    """Registra los manejadores de errores en la aplicación Flask."""

    @app.errorhandler(NotFound)
    def handle_404(error):
        """Manejador para errores 404 (No Encontrado)."""
        current_app.logger.warning(f"Ruta no encontrada: {request.path}")
        
        # Lógica para obtener la tasa de cambio y la moneda de cálculo
        company_info = CompanyInfo.query.first()
        default_currency = company_info.calculation_currency if company_info and company_info.calculation_currency else 'USD'
        calculation_currency = session.get('display_currency', default_currency)
        current_rate = get_cached_exchange_rate(calculation_currency) or 0.0
        symbol = '€' if calculation_currency == 'EUR' else '$'


        return render_template('errors/404.html', 
                               current_rate=current_rate, 
                               calculation_currency=calculation_currency,
                               currency_symbol=symbol,
                               title="Página no encontrada"), 404

    @app.errorhandler(Forbidden)
    def handle_403(error):
        """Manejador para errores 403 (Prohibido)."""
        current_app.logger.warning(f"Acceso prohibido a la ruta: {request.path} por el usuario {current_app.login_manager.current_user}")
        flash('No tienes permiso para acceder a esta página.', 'danger')
        
        # Use the injected context processor function if available, or check the role directly.
        # Redirect to the appropriate page based on role
        if current_user.is_authenticated and current_user.role not in ['Superusuario', 'Gerente']:
            return redirect(request.referrer or url_for('main.new_order'))
        else:
            return redirect(request.referrer or url_for('main.dashboard'))

    @app.errorhandler(OperationalError)
    def handle_db_connection_error(error):
        """
        Manejador específico para errores de conexión con la base de datos.
        Esto ocurre si el servidor de la base de datos no está disponible.
        """
        db.session.rollback()
        current_app.logger.error(f"Error de conexión con la base de datos: {error}", exc_info=True)
        flash('Error de Conexión: No se pudo conectar a la base de datos. Por favor, contacta al administrador del sistema.', 'danger')
        # Redirige a la página anterior para que el usuario pueda reintentar más tarde.
        return redirect(request.referrer or url_for('main.login'))

    @app.errorhandler(ConnectionError)
    def handle_network_error(error):
        """
        Manejador para errores de conexión de red al usar 'requests'.
        Esto ocurre si no hay conexión a internet al intentar consultar APIs externas.
        """
        current_app.logger.error(f"Error de red al intentar conectar a un servicio externo: {error}", exc_info=True)
        flash('Error de Red: No se pudo conectar a un servicio externo. Verifica tu conexión a internet.', 'danger')
        return redirect(request.referrer or url_for('main.dashboard'))

    @app.errorhandler(InternalServerError)
    def handle_500(error):
        """Manejador para errores internos del servidor (500)."""
        db.session.rollback()
        # El error original se encuentra en error.original_exception
        original_exception = getattr(error, "original_exception", error)
        current_app.logger.error(f"Error interno del servidor (500): {original_exception}", exc_info=True)
        flash('Ocurrió un error inesperado en el servidor. Por favor, intenta de nuevo o contacta al administrador.', 'danger')
        return redirect(request.referrer or url_for('main.login'))