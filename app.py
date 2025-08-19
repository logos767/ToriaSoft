import os
import secrets
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

# Se crea la instancia de la aplicación Flask
app = Flask(__name__)

# Configuración de la aplicación
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(16))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Se inicializan las extensiones
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# Inicializar el scheduler
scheduler = BackgroundScheduler()
scheduler.start()

@login_manager.user_loader
def load_user(user_id):
    """Carga un usuario por su ID para Flask-Login."""
    return User.query.get(int(user_id))

# --- Modelos de la Base de Datos ---

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"User('{self.username}', Admin: {self.is_admin})"

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    barcode = db.Column(db.String(50), unique=True, nullable=False)
    qr_code = db.Column(db.String(50), unique=True, nullable=False)
    image_url = db.Column(db.String(200), nullable=True)
    size = db.Column(db.String(10), nullable=False)
    color = db.Column(db.String(20), nullable=False)
    cost = db.Column(db.Float, nullable=False)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, default=0, nullable=False)

    def __repr__(self):
        return f"Product('{self.name}', '{self.barcode}')"

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.String(200), nullable=True)

    def __repr__(self):
        return f"Client('{self.name}', '{self.email}')"

class Provider(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    contact = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(20), nullable=True)

    def __repr__(self):
        return f"Provider('{self.name}')"

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    date_created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)

    client = db.relationship('Client', backref=db.backref('orders', lazy=True))

    def __repr__(self):
        return f"Order('{self.id}', '{self.status}')"

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)

    order = db.relationship('Order', backref=db.backref('items', lazy=True))
    product = db.relationship('Product', backref=db.backref('order_items', lazy=True))

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey('provider.id'), nullable=False)
    date_created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    total_cost = db.Column(db.Float, nullable=False)

    provider = db.relationship('Provider', backref=db.backref('purchases', lazy=True))

class PurchaseItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchase.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    cost = db.Column(db.Float, nullable=False)

    purchase = db.relationship('Purchase', backref=db.backref('items', lazy=True))
    product = db.relationship('Product', backref=db.backref('purchase_items', lazy=True))

class Reception(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchase.id'), nullable=False)
    date_received = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False, default='Pendiente')

    purchase = db.relationship('Purchase', backref=db.backref('receptions', lazy=True))


# Importar las rutas después de crear las instancias de db y app para evitar errores de importación circular
from routes import *

def create_db_and_initial_data():
    """Crea la base de datos y carga los datos iniciales."""
    with app.app_context():
        db.create_all()

        # Cargar usuarios predeterminados
        if not User.query.filter_by(username='admin').first():
            hashed_password = bcrypt.generate_password_hash('admin123').decode('utf-8')
            admin_user = User(username='admin', password=hashed_password, is_admin=True)
            db.session.add(admin_user)
            db.session.commit()

        if not User.query.filter_by(username='limited').first():
            hashed_password = bcrypt.generate_password_hash('limited123').decode('utf-8')
            limited_user = User(username='limited', password=hashed_password, is_admin=False)
            db.session.add(limited_user)
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


if __name__ == '__main__':
    create_db_and_initial_data()
    app.run(debug=True)
