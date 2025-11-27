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
                logger.info("Creating sequences for Store 1...")
                # Sequence for 'contado' (regular) sales
                db.session.execute(text("CREATE SEQUENCE IF NOT EXISTS order_contado_seq START 180000000"))
                # Sequence for 'credito' (credit) sales
                db.session.execute(text("CREATE SEQUENCE IF NOT EXISTS order_credito_seq START 280000000"))
                # Sequence for 'apartado' (reservation) sales
                db.session.execute(text("CREATE SEQUENCE IF NOT EXISTS order_apartado_seq START 580000000"))
                # Sequence for 'entrega especial' (special dispatch)
                db.session.execute(text("CREATE SEQUENCE IF NOT EXISTS order_entrega_especial_seq START 780000000"))

                logger.info("Creating sequences for Store 2...")
                # Sequences for the second store (sucursal 2)
                db.session.execute(text("CREATE SEQUENCE IF NOT EXISTS order_contado_seq_suc2 START 181000000"))
                db.session.execute(text("CREATE SEQUENCE IF NOT EXISTS order_credito_seq_suc2 START 281000000"))
                db.session.execute(text("CREATE SEQUENCE IF NOT EXISTS order_apartado_seq_suc2 START 581000000"))
                db.session.execute(text("CREATE SEQUENCE IF NOT EXISTS order_entrega_especial_seq_suc2 START 781000000"))

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

    @app.cli.command('fix-store2-sequences')
    def fix_store2_sequences():
        """
        Corrects order IDs for Store 2 that were incorrectly generated using Store 1's sequences.
        This command is for PostgreSQL only.
        """
        with current_app.app_context():
            if db.engine.dialect.name != 'postgresql':
                logger.error("This command is only for PostgreSQL databases.")
                return

            logger.info("Starting correction process for Store 2 order IDs...")

            # Define sequence mappings: order_type -> (store1_seq, store2_seq, store1_range)
            sequence_map = {
                'regular': ('order_contado_seq', 'order_contado_seq_suc2', (180000000, 180999999)),
                'credit': ('order_credito_seq', 'order_credito_seq_suc2', (280000000, 280999999)),
                'reservation': ('order_apartado_seq', 'order_apartado_seq_suc2', (580000000, 580999999)),
                'special_dispatch': ('order_entrega_especial_seq', 'order_entrega_especial_seq_suc2', (780000000, 780999999)),
            }

            try:
                for order_type, (s1_seq, s2_seq, s1_range) in sequence_map.items():
                    logger.info(f"Processing order type: {order_type}...")

                    # 1. Find and update incorrect orders for store 2
                    # Uses 'order' table and 'order_type' column as specified.
                    update_sql = text(f"""
                        UPDATE "order"
                        SET id = nextval('{s2_seq}')
                        WHERE store_id = 2
                          AND order_type = '{order_type}'
                          AND id >= {s1_range[0]} AND id <= {s1_range[1]};
                    """)
                    result = db.session.execute(update_sql)
                    if result.rowcount > 0:
                        logger.info(f"Corrected {result.rowcount} order(s) for order type '{order_type}' in Store 2.")
                    else:
                        logger.info(f"No incorrect orders found for '{order_type}' in Store 2.")

                    # 2. Reset Store 1 sequence to the last correct ID
                    # Find the maximum ID used correctly by Store 1 for this order type.
                    max_id_sql = text(f"""
                        SELECT MAX(id) FROM "order"
                        WHERE store_id = 1
                          AND order_type = '{order_type}'
                          AND id >= {s1_range[0]} AND id <= {s1_range[1]};
                    """)
                    max_id_result = db.session.execute(max_id_sql).scalar_one_or_none()

                    # If there are no orders for store 1, reset to the start. Otherwise, reset to max_id.
                    reset_val = max_id_result if max_id_result is not None else s1_range[0] - 1

                    # setval makes the *next* call return value + 1.
                    # If max_id is 180000005, nextval will return 180000006.
                    # If no orders exist, max_id is NULL, we reset to start-1, so next is start.
                    reset_seq_sql = text(f"SELECT setval('{s1_seq}', {reset_val});")
                    db.session.execute(reset_seq_sql)
                    logger.info(f"Reset sequence '{s1_seq}' for Store 1 to continue after {reset_val}.")

                db.session.commit()
                logger.info("Successfully corrected all sequences and order IDs.")

            except Exception as e:
                db.session.rollback()
                logger.error(f"An error occurred during the correction process: {e}")
                logger.error("The script failed. Please check your database schema and permissions.")

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
