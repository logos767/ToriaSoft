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
                
                # Create additional administrator user
                if not User.query.filter_by(username='Luis_Marin').first():
                    logger.info("Creating additional admin user Luis_Marin...")
                    hashed_password = bcrypt.generate_password_hash('Luis123').decode('utf-8')
                    admin_user = User(username='Luis_Marin', password=hashed_password, role='administrador')
                    db.session.add(admin_user)
                    db.session.commit()
                
                # Create salesperson users with limited access
                sales_users = [
                    {'username': 'vendedora1', 'password': 'Vendedora123', 'role': 'empleado'},
                    {'username': 'vendedora2', 'password': 'Vendedora456', 'role': 'empleado'}
                ]
                
                for user_data in sales_users:
                    if not User.query.filter_by(username=user_data['username']).first():
                        logger.info(f"Creating sales user {user_data['username']}...")
                        hashed_password = bcrypt.generate_password_hash(user_data['password']).decode('utf-8')
                        sales_user = User(username=user_data['username'], password=hashed_password, role=user_data['role'])
                        db.session.add(sales_user)
                        db.session.commit()
            else:
                logger.info("Table 'users' already exists, skipping table creation.")
            
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
