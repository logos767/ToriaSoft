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
            
            if not Client.query.first():
                logger.info("Creating sample clients...")
                clients = [
                    Client(name='Juan Pérez', email='juan.perez@example.com', phone='555-1234', address='Calle Falsa 123'),
                    Client(name='María López', email='maria.lopez@example.com', phone='555-5678', address='Avenida Siempre Viva 456'),
                    Client(name='Carlos Rodríguez', email='carlos.rodriguez@example.com', phone='555-9876', address='Urbanización Los Olivos')
                ]
                db.session.bulk_save_objects(clients)
                db.session.commit()

            if not Provider.query.first():
                logger.info("Creating sample providers...")
                providers = [
                    Provider(name='Provedora Textiles S.A.', contact='Ana Gómez', phone='555-9000'),
                    Provider(name='Moda Mayorista C.A.', contact='Carlos Ruiz', phone='555-9001'),
                    Provider(name='Telar de Sueños', contact='Sofía Vargas', phone='555-9002')
                ]
                db.session.bulk_save_objects(providers)
                db.session.commit()

            if not Product.query.first():
                logger.info("Creating sample products...")
                products = [
                    Product(name='Franela Algodón Blanca', description='Franela 100% algodón, cuello redondo.', barcode='000123456789', qr_code='QR0001', image_url='https://placehold.co/600x400/fff/000?text=Franela+Blanca', size='M', color='Blanco', cost_usd=5.00, price_usd=15.00, stock=50),
                    Product(name='Pantalón Jeans Azul', description='Jeans de corte recto, tela denim de alta calidad.', barcode='000987654321', qr_code='QR0002', image_url='https://placehold.co/600x400/fff/000?text=Jeans+Azul', size='32', color='Azul', cost_usd=25.00, price_usd=60.00, stock=30),
                    Product(name='Chaqueta de Cuero Negra', description='Chaqueta de cuero genuino, con forro interior.', barcode='000112233445', qr_code='QR0003', image_url='https://placehold.co/600x400/fff/000?text=Chaqueta+Negra', size='L', color='Negro', cost_usd=80.00, price_usd=200.00, stock=10),
                    Product(name='Vestido de Verano Floral', description='Vestido ligero con estampado floral, ideal para el verano.', barcode='000654321987', qr_code='QR0004', image_url='https://placehold.co/600x400/fff/000?text=Vestido+Floral', size='S', color='Floral', cost_usd=30.00, price_usd=75.00, stock=20),
                    Product(name='Suéter de Lana Gris', description='Suéter cálido de lana, ideal para el invierno.', barcode='000778899001', qr_code='QR0005', image_url='https://placehold.co/600x400/fff/000?text=Sueter+Gris', size='XL', color='Gris', cost_usd=40.00, price_usd=90.00, stock=15)
                ]
                db.session.bulk_save_objects(products)
                db.session.commit()

            logger.info("Database initialization complete!")
