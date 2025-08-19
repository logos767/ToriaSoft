from datetime import datetime
from app import db, login_manager
from flask_login import UserMixin

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='empleado') # 'empleado', 'administrador'

    def __repr__(self):
        return f"User('{self.username}', '{self.role}')"

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    barcode = db.Column(db.String(50), unique=True, nullable=False)
    qr_code = db.Column(db.String(50), unique=True, nullable=True)
    stock = db.Column(db.Integer, nullable=False, default=0)
    cost_usd = db.Column(db.Float, nullable=False, default=0.0) # Almacenado en USD
    price_usd = db.Column(db.Float, nullable=False, default=0.0) # Almacenado en USD
    image_url = db.Column(db.String(200), nullable=True)
    size = db.Column(db.String(20), nullable=True)
    color = db.Column(db.String(20), nullable=True)
    
    # Relaciones
    order_items = db.relationship('OrderItem', backref='product', lazy=True)
    purchase_items = db.relationship('PurchaseItem', backref='product', lazy=True)
    movements = db.relationship('Movement', backref='product', lazy=True)

    def __repr__(self):
        return f"Product('{self.name}', '{self.barcode}')"

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.String(200), nullable=True)
    
    # Relaciones
    orders = db.relationship('Order', backref='client', lazy=True)

    def __repr__(self):
        return f"Client('{self.name}', '{self.email}')"

class Provider(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    contact = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.String(200), nullable=True)
    
    # Relaciones
    purchases = db.relationship('Purchase', backref='provider', lazy=True)
    
    def __repr__(self):
        return f"Provider('{self.name}')"

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    date_created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False, default='Pendiente')
    total_amount = db.Column(db.Float, nullable=False, default=0.0)

    # Relaciones
    items = db.relationship('OrderItem', backref='order', lazy=True)

    def __repr__(self):
        return f"Order('{self.id}', '{self.total_amount}')"

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False) # Precio en VES en el momento de la venta

    def __repr__(self):
        return f"OrderItem('{self.order_id}', '{self.product_id}', '{self.quantity}')"
        
class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey('provider.id'), nullable=False)
    date_created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False, default='Pendiente')
    total_cost = db.Column(db.Float, nullable=False, default=0.0)

    # Relaciones
    items = db.relationship('PurchaseItem', backref='purchase', lazy=True)
    reception = db.relationship('Reception', backref='purchase', uselist=False, lazy=True)
    
    def __repr__(self):
        return f"Purchase('{self.id}', '{self.total_cost}')"

class PurchaseItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchase.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    cost = db.Column(db.Float, nullable=False) # Costo en VES en el momento de la compra

    def __repr__(self):
        return f"PurchaseItem('{self.purchase_id}', '{self.product_id}', '{self.quantity}')"

class Reception(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchase.id'), nullable=False, unique=True)
    date_received = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False, default='Pendiente')

    def __repr__(self):
        return f"Reception('{self.id}', '{self.purchase_id}')"

class Movement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'Entrada', 'Salida'
    quantity = db.Column(db.Integer, nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    document_id = db.Column(db.Integer, nullable=True) # ID de la orden, compra, etc.
    document_type = db.Column(db.String(50), nullable=True) # 'Orden de Venta', 'Orden de Compra', 'Ajuste'
    related_party_id = db.Column(db.Integer, nullable=True) # ID del cliente o proveedor
    related_party_type = db.Column(db.String(50), nullable=True) # 'Cliente', 'Proveedor'

    def __repr__(self):
        return f"Movement('{self.type}', '{self.product_id}', '{self.quantity}')"

class CompanyInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    rif = db.Column(db.String(20), unique=True, nullable=False)
    address = db.Column(db.String(200), nullable=True)
    phone_numbers = db.Column(db.String(100), nullable=True)
    logo_url = db.Column(db.String(200), nullable=True)

    def __repr__(self):
        return f"CompanyInfo('{self.name}', '{self.rif}')"

class ExchangeRate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rate = db.Column(db.Float, nullable=False)
    date_updated = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"ExchangeRate(rate='{self.rate}', date='{self.date_updated}')"
