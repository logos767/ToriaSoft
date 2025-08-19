import os
import secrets
import logging
from flask import Flask
from extensions import db, login_manager, bcrypt
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import inspect

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Se crea la instancia de la aplicación Flask
app = Flask(__name__)

# Configuración de la aplicación
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(16))

# Database configuration with error handling
database_url = os.environ.get('DATABASE_URL')
if not database_url:
    logger.error("DATABASE_URL environment variable is not set!")
    raise RuntimeError("DATABASE_URL environment variable is required")

# Fix for Heroku/Render PostgreSQL URL format
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions with app
db.init_app(app)
login_manager.init_app(app)
bcrypt.init_app(app)

login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# Inicializar el scheduler
scheduler = BackgroundScheduler()
scheduler.start()

# Importar modelos y rutas después de crear las instancias de db y app
from models import User, Product, Client, Provider, Order, OrderItem, Purchase, PurchaseItem, Reception, Movement, CompanyInfo, ExchangeRate
from routes import *

@login_manager.user_loader
def load_user(user_id):
    """Carga un usuario por su ID para Flask-Login."""
    return User.query.get(int(user_id))

def create_db_and_initial_data():
    """Crea la base de datos y carga los datos iniciales."""
    with app.app_context():
        # Usa inspect para verificar la existencia de la tabla
        inspector = inspect(db.engine)
        if not inspector.has_table('user'):
            db.create_all()
            # Cargar usuarios predeterminados
            if not User.query.filter_by(username='admin').first():
                hashed_password = bcrypt.generate_password_hash('admin123').decode('utf-8')
                admin_user = User(username='admin', password=hashed_password, role='administrador')
                db.session.add(admin_user)
                db.session.commit()

        # Cargar clientes de prueba
        if not Client.query.first():
            clients = [
                Client(name='Juan Pérez', email='juan.perez@example.com', phone='555-1234', address='Calle Falsa 123'),
                Client(name='María López', email='maria.lopez@example.com', phone='555-5678', address='Avenida Siempre Viva 456'),
                Client(name='Carlos Rodríguez', email='carlos.rodriguez@example.com', phone='555-9876', address='Urbanización Los Olivos')
            ]
            db.session.bulk_save_objects(clients)
            db.session.commit()

        # Cargar proveedores de prueba
        if not Provider.query.first():
            providers = [
                Provider(name='Provedora Textiles S.A.', contact='Ana Gómez', phone='555-9000'),
                Provider(name='Moda Mayorista C.A.', contact='Carlos Ruiz', phone='555-9001'),
                Provider(name='Telar de Sueños', contact='Sofía Vargas', phone='555-9002')
            ]
            db.session.bulk_save_objects(providers)
            db.session.commit()

        # Cargar productos de prueba
        if not Product.query.first():
            products = [
                Product(name='Franela Algodón Blanca', description='Franela 100% algodón, cuello redondo.', barcode='000123456789', qr_code='QR0001', image_url='https://placehold.co/600x400/fff/000?text=Franela+Blanca', size='M', color='Blanco', cost=5.00, price=15.00, stock=50),
                Product(name='Pantalón Jeans Azul', description='Jeans de corte recto, tela denim de alta calidad.', barcode='000987654321', qr_code='QR0002', image_url='https://placehold.co/600x400/fff/000?text=Jeans+Azul', size='32', color='Azul', cost=25.00, price=60.00, stock=30),
                Product(name='Chaqueta de Cuero Negra', description='Chaqueta de cuero genuino, con forro interior.', barcode='000112233445', qr_code='QR0003', image_url='https://placehold.co/600x400/fff/000?text=Chaqueta+Negra', size='L', color='Negro', cost=80.00, price=200.00, stock=10),
                Product(name='Vestido de Verano Floral', description='Vestido ligero con estampado floral, ideal para el verano.', barcode='000654321987', qr_code='QR0004', image_url='https://placehold.co/600x400/fff/000?text=Vestido+Floral', size='S', color='Floral', cost=30.00, price=75.00, stock=20),
                Product(name='Suéter de Lana Gris', description='Suéter cálido de lana, ideal para el invierno.', barcode='000778899001', qr_code='QR0005', image_url='https://placehold.co/600x400/fff/000?text=Sueter+Gris', size='XL', color='Gris', cost=40.00, price=90.00, stock=15)
            ]
            db.session.bulk_save_objects(products)
            db.session.commit()

# **Llamada a la función fuera del if __name__ == '__main__':**
create_db_and_initial_data()

if __name__ == '__main__':
    app.run(debug=True)