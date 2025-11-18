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
                # Sequence for 'entrega especial' (special dispatch)
                db.session.execute(text("CREATE SEQUENCE IF NOT EXISTS order_entrega_especial_seq START 780000000"))
                db.session.commit()
                
                logger.info("Successfully created or verified order ID sequences.")
            except Exception as e:
                db.session.rollback()
                logger.error(f"Failed to create order ID sequences: {e}")
                logger.error("This command is only compatible with PostgreSQL.")

    @app.cli.command('reset-sequences')
    def reset_sequences():
        """
        Resets all primary key sequences in the database to the max ID of their
        respective tables. Useful after manual data insertion. (PostgreSQL only).
        """
        with current_app.app_context():
            if db.engine.dialect.name != 'postgresql':
                logger.error("This command is only for PostgreSQL databases.")
                return

            logger.info("Starting sequence reset for all tables...")
            
            inspector = inspect(db.engine)
            all_table_names = inspector.get_table_names()

            for table_name in all_table_names:
                # The default sequence name for a primary key 'id' is 'table_name_id_seq'
                sequence_name = f"{table_name}_id_seq"
                try:
                    # This SQL command gets the max ID from the table and sets the sequence to that value.
                    # The next call to nextval() will return max(id) + 1.
                    sql = text(f"SELECT setval('{sequence_name}', (SELECT MAX(id) FROM {table_name}));")
                    db.session.execute(sql)
                    db.session.commit()
                    logger.info(f"Successfully reset sequence '{sequence_name}' for table '{table_name}'.")
                except Exception as e:
                    # This might fail if a table doesn't have an 'id' sequence, which is fine.
                    logger.warning(f"Could not reset sequence for table '{table_name}'. It might not have a standard 'id' sequence. Error: {e}")
                    db.session.rollback()
            
            logger.info("Sequence reset process finished.")

    @app.cli.command('clean-db-schema')
    def clean_db_schema():
        """
        Detects and removes obsolete columns from the database schema to match the models.
        """
        with current_app.app_context():
            if db.engine.dialect.name != 'postgresql':
                logger.error("This command is only for PostgreSQL databases.")
                return

            logger.info("Checking for obsolete columns in the database schema...")
            inspector = inspect(db.engine)
            
            # Check for obsolete 'stock' column in 'product' table
            columns = inspector.get_columns('product')
            if any(c['name'] == 'stock' for c in columns):
                logger.warning("Obsolete 'stock' column found in 'product' table. Attempting to remove it...")
                try:
                    db.session.execute(text('ALTER TABLE product DROP COLUMN stock;'))
                    db.session.commit()
                    logger.info("Successfully removed 'stock' column from 'product' table.")
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Failed to remove 'stock' column: {e}")
            else:
                logger.info("'product' table schema is up to date (no 'stock' column found).")
