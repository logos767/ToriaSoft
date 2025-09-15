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

    @app.cli.command('init-order-sequences')
    def init_order_sequences():
        """Initializes the order ID sequences for different sale types (PostgreSQL only)."""
        with current_app.app_context():
            try:
                # Sequence for 'contado' (regular) sales
                db.session.execute(text("CREATE SEQUENCE IF NOT EXISTS order_contado_seq START 180000000"))
                # Sequence for 'credito' (credit) sales
                db.session.execute(text("CREATE SEQUENCE IF NOT EXISTS order_credito_seq START 280000000"))
                # Sequence for 'apartado' (reservation) sales
                db.session.execute(text("CREATE SEQUENCE IF NOT EXISTS order_apartado_seq START 580000000"))
                db.session.commit()
                logger.info("Successfully created or verified order ID sequences.")
            except Exception as e:
                db.session.rollback()
                logger.error(f"Failed to create order ID sequences: {e}")
                logger.error("This command is only compatible with PostgreSQL.")
