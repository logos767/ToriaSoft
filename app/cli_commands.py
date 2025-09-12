import logging
from flask import current_app
from sqlalchemy import inspect, text
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
            else:
                logger.info("Tables already exist. Creating missing tables if any...")
                # This ensures that if a new model was added, its table gets created.
                db.create_all()
            
            # ... (The rest of your data loading logic for clients, providers, products) ...
            
            if not Client.query.first():
                logger.info("Creating sample clients...")
                clients = [
                    
                ]
                db.session.bulk_save_objects(clients)
                db.session.commit()

            if not Provider.query.first():
                logger.info("Creating sample providers...")
                providers = [
                    
                ]
                db.session.bulk_save_objects(providers)
                db.session.commit()

            if not Product.query.first():
                logger.info("Creating sample products...")
                products = [
                    
                ]
                db.session.bulk_save_objects(products)
                db.session.commit()

            logger.info("Database initialization complete!")

    @app.cli.command('set-order-start')
    def set_order_start_number():
        """Sets the starting number for the order ID sequence to 18070001."""
        with current_app.app_context():
            try:
                # This command is specific to PostgreSQL.
                # The sequence name is typically <table_name>_<id_column_name>_seq
                db.session.execute(text("ALTER SEQUENCE order_id_seq RESTART WITH 18070001"))
                db.session.commit()
                logger.info("Successfully set the order ID sequence to start at 18070001.")
            except Exception as e:
                db.session.rollback()
                logger.error(f"Failed to set order ID sequence: {e}")
                logger.error("This command is likely only compatible with PostgreSQL. Make sure the 'order' table exists.")
