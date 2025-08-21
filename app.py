import logging
import os
import secrets
from dotenv import load_dotenv
from flask import Flask
from flask_socketio import SocketIO
from extensions import db, login_manager, bcrypt
from sqlalchemy import inspect

# Carga las variables de entorno desde el archivo .env (solo para desarrollo local)
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Configuration ---
# Load configuration directly instead of from a file for better deployment reliability.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(16))

# Database configuration with error handling and auto-correction for Render's URL format.
database_url = os.environ.get('DATABASE_URL')
if not database_url:
    logger.critical("FATAL: DATABASE_URL environment variable is not set!")
    raise RuntimeError("DATABASE_URL environment variable is required")

if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db.init_app(app)
bcrypt.init_app(app)
login_manager.init_app(app)

login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

socketio = SocketIO(app, async_mode='eventlet')

def update_exchange_rate_task():
    """
    Tarea en segundo plano para actualizar la tasa de cambio cada hora.
    Utiliza socketio.sleep para ser compatible con eventlet.
    """
    logger.info("La tarea de actualización de tasa de cambio en segundo plano está lista para iniciarse.")
    # Añadir un pequeño retraso inicial para asegurar que la app esté completamente iniciada
    socketio.sleep(10)
    while True:
        try:
            with app.app_context():
                logger.info("Ejecutando actualización de tasa de cambio...")
                from utils import obtener_tasa_p2p_binance # Importar aquí para evitar dependencias circulares
                new_rate = obtener_tasa_p2p_binance()
                if new_rate:
                    rate_entry = ExchangeRate.query.first()
                    if not rate_entry:
                        rate_entry = ExchangeRate(rate=new_rate)
                        db.session.add(rate_entry)
                    else:
                        rate_entry.rate = new_rate
                    db.session.commit()
                    logger.info(f"Tasa de cambio actualizada a: {new_rate}")
                else:
                    logger.warning("No se obtuvo una nueva tasa de cambio en esta ejecución.")
        except Exception as e:
            logger.error(f"Error en la tarea de actualización de tasa de cambio: {e}", exc_info=True)
            # Asegurarse de revertir la sesión de la base de datos en caso de error
            with app.app_context():
                db.session.rollback()
        # Esperar 1 hora (3600 segundos) antes de la siguiente ejecución
        socketio.sleep(3600)

# Importar modelos y rutas después de crear las instancias de db y app
from models import User, Product, Client, Provider, Order, OrderItem, Purchase, PurchaseItem, Reception, Movement, CompanyInfo, ExchangeRate
from routes import routes_blueprint

@login_manager.user_loader
def load_user(user_id):
    """Carga un usuario por su ID para Flask-Login."""
    return User.query.get(int(user_id))

@app.cli.command('init-db')
def create_db_and_initial_data():
    """Crea la base de datos y carga los datos iniciales."""
    with app.app_context():
        # Usa inspect para verificar la existencia de la tabla
        inspector = inspect(db.engine)
        if not inspector.has_table('user'):
            logger.info("Creando todas las tablas de la base de datos...")
            db.create_all()
            # Cargar usuarios predeterminados
            if not User.query.filter_by(username='admin').first():
                logger.info("Creando usuario administrador predeterminado...")
                hashed_password = bcrypt.generate_password_hash('admin123').decode('utf-8')
                admin_user = User(username='admin', password=hashed_password, role='administrador')
                db.session.add(admin_user)
                db.session.commit()
        else:
            logger.info("La tabla 'user' ya existe, omitiendo la creación de tablas.")

        # Cargar clientes de prueba
        if not Client.query.first():
            logger.info("Cargando clientes de prueba...")
            clients = [
                Client(name='Juan Pérez', email='juan.perez@example.com', phone='555-1234', address='Calle Falsa 123'),
                Client(name='María López', email='maria.lopez@example.com', phone='555-5678', address='Avenida Siempre Viva 456'),
                Client(name='Carlos Rodríguez', email='carlos.rodriguez@example.com', phone='555-9876', address='Urbanización Los Olivos')
            ]
            db.session.bulk_save_objects(clients)
            db.session.commit()
        else:
            logger.info("Ya existen clientes en la base de datos, omitiendo carga.")

        # Cargar proveedores de prueba
        if not Provider.query.first():
            logger.info("Cargando proveedores de prueba...")
            providers = [
                Provider(name='Provedora Textiles S.A.', contact='Ana Gómez', phone='555-9000'),
                Provider(name='Moda Mayorista C.A.', contact='Carlos Ruiz', phone='555-9001'),
                Provider(name='Telar de Sueños', contact='Sofía Vargas', phone='555-9002')
            ]
            db.session.bulk_save_objects(providers)
            db.session.commit()
        else:
            logger.info("Ya existen proveedores en la base de datos, omitiendo carga.")

        # Cargar productos de prueba
        if not Product.query.first():
            logger.info("Cargando productos de prueba...")
            products = [
                Product(name='Franela Algodón Blanca', description='Franela 100% algodón, cuello redondo.', barcode='000123456789', qr_code='QR0001', image_url='https://placehold.co/600x400/fff/000?text=Franela+Blanca', size='M', color='Blanco', cost_usd=5.00, price_usd=15.00, stock=50),
                Product(name='Pantalón Jeans Azul', description='Jeans de corte recto, tela denim de alta calidad.', barcode='000987654321', qr_code='QR0002', image_url='https://placehold.co/600x400/fff/000?text=Jeans+Azul', size='32', color='Azul', cost_usd=25.00, price_usd=60.00, stock=30),
                Product(name='Chaqueta de Cuero Negra', description='Chaqueta de cuero genuino, con forro interior.', barcode='000112233445', qr_code='QR0003', image_url='https://placehold.co/600x400/fff/000?text=Chaqueta+Negra', size='L', color='Negro', cost_usd=80.00, price_usd=200.00, stock=10),
                Product(name='Vestido de Verano Floral', description='Vestido ligero con estampado floral, ideal para el verano.', barcode='000654321987', qr_code='QR0004', image_url='https://placehold.co/600x400/fff/000?text=Vestido+Floral', size='S', color='Floral', cost_usd=30.00, price_usd=75.00, stock=20),
                Product(name='Suéter de Lana Gris', description='Suéter cálido de lana, ideal para el invierno.', barcode='000778899001', qr_code='QR0005', image_url='https://placehold.co/600x400/fff/000?text=Sueter+Gris', size='XL', color='Gris', cost_usd=40.00, price_usd=90.00, stock=15)
            ]
            db.session.bulk_save_objects(products)
            db.session.commit()
        else:
            logger.info("Ya existen productos en la base de datos, omitiendo carga.")
        logger.info("¡Inicialización de la base de datos completada!")

app.register_blueprint(routes_blueprint)

# The background task is now started via Gunicorn's post_worker_init hook.

if __name__ == '__main__':
    # Para ejecutar con SocketIO en desarrollo, usa socketio.run
    socketio.run(app, debug=True)