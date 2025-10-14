import logging
import os
import secrets
import firebase_admin
from firebase_admin import credentials
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

def initialize_firebase(app):
    """Initializes the Firebase Admin SDK."""
    with app.app_context():
        try:
            # La ruta al archivo de credenciales. Asume que está en la raíz del proyecto.
            cred_path = os.path.join(app.root_path, '..', 'firebase-adminsdk.json')
            if os.path.exists(cred_path):
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
                logger.info("Firebase Admin SDK inicializado correctamente.")
            else:
                logger.error("ERROR: No se encontró el archivo 'firebase-adminsdk.json'. Las notificaciones FCM no funcionarán.")
        except Exception as e:
            logger.error(f"Error al inicializar Firebase Admin SDK: {e}")

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
        if not User.query.filter_by(username='luismarin').first():
            logger.info("Creating Superuser luismarin...")
            hashed_password = bcrypt.generate_password_hash('7671010').decode('utf-8')
            users_to_add.append(User(username='luismarin', password=hashed_password, role='Superusuario'))

        # Additional admin user
        if not User.query.filter_by(username='contastij').first():
            logger.info("Creating Gerente contastij...")
            hashed_password = bcrypt.generate_password_hash('admin1807').decode('utf-8')
            users_to_add.append(User(username='contastij', password=hashed_password, role='Gerente'))

        # Additional admin user
        if not User.query.filter_by(username='emarquez').first():
            logger.info("Creating Contador emarquez...")
            hashed_password = bcrypt.generate_password_hash('admin1208').decode('utf-8')
            users_to_add.append(User(username='emarquez', password=hashed_password, role='Contador'))

        # Additional admin user
        if not User.query.filter_by(username='mcastellanos').first():
            logger.info("Creating Contador mcastellanos...")
            hashed_password = bcrypt.generate_password_hash('mg251807').decode('utf-8')
            users_to_add.append(User(username='mcastellanos', password=hashed_password, role='Contador'))


        # Salesperson users
        sales_users_data = [
            {'username': 'paula', 'password': 'paula123', 'role': 'Vendedor'},
            {'username': 'vendedora2', 'password': 'Vendedora456', 'role': 'Vendedor'}
        ]
        for user_data in sales_users_data:
            if not User.query.filter_by(username=user_data['username']).first():
                logger.info(f"Creating Vendedor user {user_data['username']}...")
                hashed_password = bcrypt.generate_password_hash(user_data['password']).decode('utf-8')
                users_to_add.append(User(username=user_data['username'], password=hashed_password, role='Vendedor'))
        
        if users_to_add:
            db.session.add_all(users_to_add)
            db.session.commit()
            logger.info(f"Added {len(users_to_add)} new users to the database.")

def create_order_sequences(app):
    """Creates the order ID sequences if they don't exist (PostgreSQL only)."""
    with app.app_context():
        from sqlalchemy import text
        # This check is important for environments that might not be PostgreSQL
        if db.engine.dialect.name != 'postgresql':
            logger.info("Skipping sequence creation for non-PostgreSQL database.")
            return
        try:
            logger.info("Verifying or creating order ID sequences for PostgreSQL...")
            db.session.execute(text("CREATE SEQUENCE IF NOT EXISTS order_contado_seq START 180000000"))
            db.session.execute(text("CREATE SEQUENCE IF NOT EXISTS order_credito_seq START 280000000"))
            db.session.execute(text("CREATE SEQUENCE IF NOT EXISTS order_apartado_seq START 580000000"))
            db.session.commit()
            logger.info("Order ID sequences are ready.")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to create order ID sequences: {e}")
            logger.error("This feature is only compatible with PostgreSQL. The app may not function correctly.")


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

    # --- Import and Register Blueprints & Models ---
    with app.app_context():
        from . import routes
        from . import models # Ensures models are registered with SQLAlchemy
        
        # Create database tables if they don't exist.
        # This is crucial for the first run or when the database is empty.
        logger.info("Ensuring all database tables exist...")
        db.create_all()
        
        app.register_blueprint(routes.routes_blueprint)

        login_manager.login_view = 'main.login' # Note: 'main.' prefix from blueprint
        login_manager.login_message_category = 'info'

        # Define user loader inside the factory
        @login_manager.user_loader
        def load_user(user_id):
            return models.User.query.get(int(user_id))

        # Register CLI commands
        from .cli_commands import register_commands
        register_commands(app)

        # Registrar manejadores de errores
        from .error_handlers import register_error_handlers
        register_error_handlers(app)

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

        # Inject role helper functions into all templates
        @app.context_processor
        def inject_role_helpers():
            from .routes import is_superuser, is_gerente, is_contador, is_vendedor
            return dict(
                is_superuser=is_superuser,
                is_gerente=is_gerente,
                is_contador=is_contador,
                is_vendedor=is_vendedor
            )

        # Bank icons dictionary
        BANK_ICONS = {
            'BBVA PROVINCIAL': '0108.png',
            'Banesco Panama': '0134.png',
            'ZELLE davidamaciasp@gmail.com': '0053.png',
            'Efectivo VES': 'VES.png',
            'Efectivo USD': 'USD.png'
        }

        @app.context_processor
        def inject_bank_icons():
            # Make the dictionary available to all templates
            return dict(BANK_ICONS=BANK_ICONS)

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.session.remove()

    # --- Initialize Firebase ---
    initialize_firebase(app)

    # --- Initial data fetch ---
    initial_exchange_rate_fetch(app)

    # --- Create initial users if they don't exist ---
    create_initial_users(app)

    # --- Create order sequences if they don't exist (for PostgreSQL) ---
    create_order_sequences(app)

    return app
