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
