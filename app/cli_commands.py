import logging
from flask import current_app
from sqlalchemy import inspect
from .extensions import db, bcrypt
from .models import User, Client, Provider, Product

logger = logging.getLogger(__name__)

def register_commands(app):
    @app.cli.command('init-db')
    def create_db_and_initial_data():
        """Creates the database and loads initial data."""
        with current_app.app_context():
            inspector = inspect(db.engine)
            if not inspector.has_table('users'):
                logger.info("Creating all database tables...")
                db.create_all()
                if not User.query.filter_by(username='admin').first():
                    logger.info("Creating default admin user...")
                    hashed_password = bcrypt.generate_password_hash('admin123').decode('utf-8')
                    admin_user = User(username='admin', password=hashed_password, role='administrador')
                    db.session.add(admin_user)
                    db.session.commit()
            else:
                logger.info("Table 'users' already exists, skipping table creation.")
            
            # ... (The rest of your data loading logic for clients, providers, products) ...
            logger.info("Database initialization complete!")
