import logging
import os
import secrets
from dotenv import load_dotenv
from flask import Flask

# Import extensions
from .extensions import db, login_manager, bcrypt, socketio

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        
        app.register_blueprint(routes.routes_blueprint)

        # Define user loader inside the factory
        @login_manager.user_loader
        def load_user(user_id):
            return models.User.query.get(int(user_id))

        # Register CLI commands
        from .cli_commands import register_commands
        register_commands(app)

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.session.remove()


    return app