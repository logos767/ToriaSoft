import logging
import os
import secrets
from dotenv import load_dotenv
from flask import Flask


# Import extensions
from .extensions import db, login_manager, bcrypt, socketio
from .routes import fetch_and_update_exchange_rate

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def initial_exchange_rate_fetch(app):
    """Fetch exchange rate once on application startup."""
    with app.app_context():
        logger.info("Performing initial exchange rate fetch...")
        rate = fetch_and_update_exchange_rate()
        if rate:
            logger.info(f"Initial exchange rate set to: {rate}")
        else:
            logger.warning("Could not fetch initial exchange rate. The application might not work as expected.")

def create_initial_users(app):
    """Creates the default users if they don't exist when the app starts."""
    with app.app_context():
        from .models import User
        from .extensions import bcrypt

        # Using a single commit for efficiency
        users_to_add = []

        # Admin user
        if not User.query.filter_by(username='admin').first():
            logger.info("Creating default admin user...")
            hashed_password = bcrypt.generate_password_hash('admin123').decode('utf-8')
            users_to_add.append(User(username='admin', password=hashed_password, role='administrador'))

        # Additional admin user
        if not User.query.filter_by(username='Luis_Marin').first():
            logger.info("Creating additional admin user Luis_Marin...")
            hashed_password = bcrypt.generate_password_hash('Luis123').decode('utf-8')
            users_to_add.append(User(username='Luis_Marin', password=hashed_password, role='administrador'))

        # Salesperson users
        sales_users_data = [
            {'username': 'vendedora1', 'password': 'Vendedora123', 'role': 'empleado'},
            {'username': 'vendedora2', 'password': 'Vendedora456', 'role': 'empleado'}
        ]
        for user_data in sales_users_data:
            if not User.query.filter_by(username=user_data['username']).first():
                logger.info(f"Creating sales user {user_data['username']}...")
                hashed_password = bcrypt.generate_password_hash(user_data['password']).decode('utf-8')
                users_to_add.append(User(username=user_data['username'], password=hashed_password, role=user_data['role']))
        
        if users_to_add:
            db.session.add_all(users_to_add)
            db.session.commit()
            logger.info(f"Added {len(users_to_add)} new users to the database.")

def create_app():
    """Application Factory Function"""
    app = Flask(__name__)

    # --- Configuration ---
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(16))
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        logger.critical("FATAL: DATABASE_URL environment variable is not set!")
        raise RuntimeError("DATABASE_URL environment variable is required")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # Engine options to handle database connection issues (e.g., "server closed the connection unexpectedly")
    # 'pool_pre_ping': checks if a connection is alive before using it from the pool.
    # 'pool_recycle': recycles connections after a set time (in seconds). This is useful for DBs that time out idle connections.
    # A value of 280 is safe for many default DB timeouts (e.g., 300s).
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    # --- Initialize Extensions ---
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    socketio.init_app(app)

    # Attach socketio to the app object so we can access it in run.py
    app.socketio = socketio

    login_manager.login_view = 'main.login' # Note: 'main.' prefix from blueprint
    login_manager.login_message_category = 'info'

    # --- Import and Register Blueprints & Models ---
    with app.app_context():
        from . import routes
        from . import models # Ensures models are registered with SQLAlchemy
        
        # Create database tables if they don't exist.
        # This is crucial for the first run or when the database is empty.
        logger.info("Ensuring all database tables exist...")
        db.create_all()
        
        app.register_blueprint(routes.routes_blueprint)

        # Define user loader inside the factory
        @login_manager.user_loader
        def load_user(user_id):
            return models.User.query.get(int(user_id))

        # Register CLI commands
        from .cli_commands import register_commands
        register_commands(app)

        # Custom Jinja filter for Venezuela timezone formatting
        @app.template_filter('ve_datetime')
        def ve_datetime_filter(dt, fmt='%d/%m/%Y %H:%M:%S'):
            if not dt:
                return ''
            # The datetime objects from the DB are timezone-aware (UTC).
            # We convert them to Venezuela's timezone before formatting.
            return dt.astimezone(models.VE_TIMEZONE).strftime(fmt)

        @app.template_filter('order_id_format')
        def order_id_format_filter(order_id):
            if not order_id:
                return ''
            return f"{order_id:09d}"

        # Add get_current_time_ve to context for use in templates
        @app.context_processor
        def inject_ve_time():
            return dict(get_current_time_ve=models.get_current_time_ve)

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.session.remove()

    # --- Initial data fetch ---
    initial_exchange_rate_fetch(app)

    # --- Create initial users if they don't exist ---
    create_initial_users(app)

    return app
