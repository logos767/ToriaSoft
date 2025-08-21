import logging
import os
import secrets
import sys

# --- PASO 0: CRÍTICO - Configurar logging para capturar TODO desde el inicio ---
# Esto asegura que veamos los errores incluso antes de que Flask se inicialice.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    stream=sys.stdout  # Dirigir logs a la salida estándar, que Render captura
)

try:
	logging.info("PASO 1: Iniciando secuencia de importación de la aplicación.")
	from dotenv import load_dotenv
	from flask import Flask
	from flask_socketio import SocketIO
	from extensions import db, login_manager, bcrypt
	from sqlalchemy import inspect
	logging.info("PASO 2: Librerías principales importadas exitosamente.")

	load_dotenv()
	logging.info("PASO 3: Archivo .env procesado.")

	app = Flask(__name__)
	logging.info("PASO 4: Instancia de la aplicación Flask creada.")

	# Configuración de la aplicación
	app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(16))

	# Configuración de la base de datos con manejo de errores
	database_url = os.environ.get('DATABASE_URL')
	if not database_url:
		logging.critical("FATAL: La variable de entorno DATABASE_URL no está configurada.")
		raise RuntimeError("DATABASE_URL environment variable is required")

	# Corrección para el formato de URL de PostgreSQL de Heroku/Render
	if database_url.startswith("postgres://"):
		database_url = database_url.replace("postgres://", "postgresql://", 1)

	app.config['SQLALCHEMY_DATABASE_URI'] = database_url
	app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
	logging.info("PASO 5: Configuración de la aplicación cargada.")

	# Inicializar extensiones con la app
	db.init_app(app)
	login_manager.init_app(app)
	bcrypt.init_app(app)
	login_manager.login_view = 'login'
	login_manager.login_message_category = 'info'
	logging.info("PASO 6: Extensiones de Flask inicializadas.")

	socketio = SocketIO(app, async_mode='eventlet')
	logging.info("PASO 7: SocketIO inicializado.")

	def update_exchange_rate_task():
		"""
		Tarea en segundo plano para actualizar la tasa de cambio cada hora.
		Utiliza socketio.sleep para ser compatible con eventlet.
		"""
		logging.info("La tarea de actualización de tasa de cambio en segundo plano está lista para iniciarse.")
		socketio.sleep(10)
		while True:
			try:
				with app.app_context():
					logging.info("Ejecutando actualización de tasa de cambio...")
					from utils import obtener_tasa_p2p_binance
					new_rate = obtener_tasa_p2p_binance()
					if new_rate:
						rate_entry = ExchangeRate.query.first()
						if not rate_entry:
							rate_entry = ExchangeRate(rate=new_rate)
							db.session.add(rate_entry)
						else:
							rate_entry.rate = new_rate
						db.session.commit()
						logging.info(f"Tasa de cambio actualizada a: {new_rate}")
					else:
						logging.warning("No se obtuvo una nueva tasa de cambio en esta ejecución.")
			except Exception as e:
				logging.error(f"Error en la tarea de actualización de tasa de cambio: {e}", exc_info=True)
				with app.app_context():
					db.session.rollback()
			socketio.sleep(3600)
	logging.info("PASO 8: Función de tarea en segundo plano definida.")

	from models import User, Product, Client, Provider, Order, OrderItem, Purchase, PurchaseItem, Reception, Movement, CompanyInfo, ExchangeRate
	logging.info("PASO 9: Módulo 'models' importado.")
	from routes import routes_blueprint
	logging.info("PASO 10: Módulo 'routes' importado.")

	@login_manager.user_loader
	def load_user(user_id):
		"""Carga un usuario por su ID para Flask-Login."""
		return User.query.get(int(user_id))
	logging.info("PASO 11: User loader registrado.")

	@app.cli.command('init-db')
	def create_db_and_initial_data():
		"""Crea la base de datos y carga los datos iniciales."""
		with app.app_context():
			inspector = inspect(db.engine)
			if not inspector.has_table('user'):
				logging.info("Creando todas las tablas de la base de datos...")
				db.create_all()
				if not User.query.filter_by(username='admin').first():
					logging.info("Creando usuario administrador predeterminado...")
					hashed_password = bcrypt.generate_password_hash('admin123').decode('utf-8')
					admin_user = User(username='admin', password=hashed_password, role='administrador')
					db.session.add(admin_user)
					db.session.commit()
			else:
				logging.info("La tabla 'user' ya existe, omitiendo la creación de tablas.")

			if not Client.query.first():
				logging.info("Cargando clientes de prueba...")
				clients = [
					Client(name='Juan Pérez', email='juan.perez@example.com', phone='555-1234', address='Calle Falsa 123'),
					Client(name='María López', email='maria.lopez@example.com', phone='555-5678', address='Avenida Siempre Viva 456'),
					Client(name='Carlos Rodríguez', email='carlos.rodriguez@example.com', phone='555-9876', address='Urbanización Los Olivos')
				]
				db.session.bulk_save_objects(clients)
				db.session.commit()
			else:
				logging.info("Ya existen clientes en la base de datos, omitiendo carga.")

			if not Provider.query.first():
				logging.info("Cargando proveedores de prueba...")
				providers = [
					Provider(name='Provedora Textiles S.A.', contact='Ana Gómez', phone='555-9000'),
					Provider(name='Moda Mayorista C.A.', contact='Carlos Ruiz', phone='555-9001'),
					Provider(name='Telar de Sueños', contact='Sofía Vargas', phone='555-9002')
				]
				db.session.bulk_save_objects(providers)
				db.session.commit()
			else:
				logging.info("Ya existen proveedores en la base de datos, omitiendo carga.")

			if not Product.query.first():
				logging.info("Cargando productos de prueba...")
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
				logging.info("Ya existen productos en la base de datos, omitiendo carga.")
			logging.info("¡Inicialización de la base de datos completada!")
	logging.info("PASO 12: Comando 'init-db' registrado.")

	app.register_blueprint(routes_blueprint)
	logging.info("PASO 13: Blueprint registrado.")

	logging.info("--- ÉXITO: El módulo app.py se ha importado y configurado completamente. ---")

except Exception as e:
    logging.critical(f"--- ERROR FATAL DURANTE EL ARRANQUE en app.py: {e}", exc_info=True)
    raise

if __name__ == '__main__':
    # Para ejecutar con SocketIO en desarrollo, usa socketio.run
    socketio.run(app, debug=True)