from datetime import datetime
import pytz
import re
import os
from flask import current_app, url_for

# Define la zona horaria de Venezuela (GMT-4)
VE_TIMEZONE = pytz.timezone('America/Caracas')

def get_current_time_ve():
    """Retorna la hora actual en la zona horaria de Venezuela."""
    return datetime.now(VE_TIMEZONE)

from .extensions import db
from sqlalchemy import func
from flask_login import UserMixin

class Store(db.Model):
    __tablename__ = 'stores'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    def __repr__(self):
        return f"Store('{self.name}')"

user_stores = db.Table('user_stores',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('store_id', db.Integer, db.ForeignKey('stores.id'), primary_key=True)
)

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='empleado') # 'empleado', 'administrador'
    is_active_status = db.Column(db.Boolean, nullable=False, default=True)

    # --- Campos del Perfil de Usuario ---
    first_name = db.Column(db.String(50), nullable=True)
    last_name = db.Column(db.String(50), nullable=True)
    doc_type = db.Column(db.String(1), nullable=True)
    doc_number = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    address = db.Column(db.Text, nullable=True)
    profile_image_file = db.Column(db.String(20), nullable=False, default='default.png')
    social_facebook = db.Column(db.String(100), nullable=True)
    social_instagram = db.Column(db.String(100), nullable=True)
    social_x = db.Column(db.String(100), nullable=True)
    bank_name = db.Column(db.String(100), nullable=True)
    bank_account_number = db.Column(db.String(25), nullable=True)
    
    # Relación con Sucursales
    stores = db.relationship('Store', secondary=user_stores, lazy='subquery',
                             backref=db.backref('users', lazy=True))
    @property
    def is_active(self):
        """Sobrescribe la propiedad de Flask-Login para usar nuestro campo de la BD."""
        return self.is_active_status

    def __repr__(self):
        return f"User('{self.username}', '{self.role}')"

class UserDevice(db.Model):
    __tablename__ = 'user_devices'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # fcm_token puede ser un token de FCM o una suscripción web push en formato JSON
    fcm_token = db.Column(db.Text, unique=True, nullable=False)
    device_type = db.Column(db.String(50), nullable=True, default='android') # 'android', 'ios', 'web'
    last_login = db.Column(db.DateTime(timezone=True), default=get_current_time_ve, onupdate=get_current_time_ve, index=True)

    user = db.relationship('User', backref=db.backref('devices', lazy='dynamic', cascade="all, delete-orphan"))

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    barcode = db.Column(db.String(50), unique=True, nullable=False)
    qr_code = db.Column(db.String(50), unique=True, nullable=True)
    cost_usd = db.Column(db.Float, nullable=False, default=0.0) # Almacenado en USD
    price_usd = db.Column(db.Float, nullable=False, default=0.0) # Almacenado en USD
    image_url = db.Column(db.String(200), nullable=True)
    size = db.Column(db.String(20), nullable=True)
    color = db.Column(db.String(120), nullable=True)
    codigo_producto = db.Column(db.String(50), nullable=True)
    marca = db.Column(db.String(50), nullable=True)
    grupo = db.Column(db.String(50), nullable=True, index=True)
    profit_margin = db.Column(db.Float, nullable=False, default=0.20) # Margen de utilidad (ej. 20%)
    specific_freight_cost = db.Column(db.Float, nullable=False, default=0) # Costo de flete específico por unidad
    estimated_monthly_sales = db.Column(db.Integer, nullable=False, default=1) # Ventas estimadas para distribuir costos fijos
    variable_selling_expense_percent = db.Column(db.Float, nullable=False, default=0) # % de gasto de venta (si es diferente al global)
    variable_marketing_percent = db.Column(db.Float, nullable=False, default=0) # % de marketing (si es diferente al global)
    
    # Relaciones
    order_items = db.relationship('OrderItem', backref='product', lazy=True)
    purchase_items = db.relationship('PurchaseItem', backref='product', lazy=True)
    movements = db.relationship('Movement', backref='product', lazy='dynamic')
    stock_levels = db.relationship('ProductStock', backref='product', lazy='joined', cascade="all, delete-orphan")

    @property
    def display_image_url(self):
        """
        Returns the specific image URL if it exists, otherwise returns a default
        image URL based on the product's group, or a final fallback default image.
        """
        if self.image_url:
            # Check if the image_url is a full URL or a local path
            if self.image_url.startswith('http://') or self.image_url.startswith('https://'):
                return self.image_url
            # It's a local path, generate URL
            return url_for('static', filename=self.image_url)

        # If no specific image, try group-based default
        if self.grupo:
            # Sanitize group name to create a valid filename
            sanitized_group_name = re.sub(r'[^a-zA-Z0-9]+', '_', self.grupo).lower()
            group_image_filename = f"img/productos/{sanitized_group_name}.png"
            group_image_path = os.path.join(current_app.root_path, 'static', group_image_filename)
            if os.path.exists(group_image_path):
                return url_for('static', filename=group_image_filename)
        # Fallback to the ultimate default image
        return url_for('static', filename='img/productos/default.png')
    @property
    def stock(self):
        """Calcula el stock total sumando las existencias de todos los almacenes."""
        return sum(level.quantity for level in self.stock_levels)

    @property
    def stock_tienda(self):
        """Retorna el stock específico del almacén principal (ID=1, '01 - Tienda')."""
        # Iterar sobre la lista de niveles de stock ya cargada
        stock_tienda = next((level for level in self.stock_levels if level.warehouse_id == 1), None)
        return stock_tienda.quantity if stock_tienda else 0

    def __repr__(self):
        return f"Product('{self.name}', '{self.barcode}')"

class Warehouse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    is_sellable = db.Column(db.Boolean, default=False, nullable=False, index=True) # Indica si se puede vender desde este almacén
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False, index=True)

    # Relación con Sucursal
    store = db.relationship('Store', backref=db.backref('warehouses', lazy='dynamic'))

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    cedula_rif = db.Column(db.String(40), nullable=True)
    email = db.Column(db.String(120), unique=False, nullable=True)
    phone = db.Column(db.String(40), nullable=True)
    address = db.Column(db.String(200), nullable=True)
    
    # Columna para asociar este cliente con un registro de proveedor
    provider_id = db.Column(db.Integer, db.ForeignKey('provider.id'), nullable=True, unique=True)
    credit_balance_usd = db.Column(db.Numeric(10, 2), default=0.0, nullable=False)


    # Relaciones
    orders = db.relationship('Order', backref='client', lazy=True)
    credit_movements = db.relationship('ClientCreditMovement', backref='client', lazy=True, cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"Client('{self.name}', '{self.email}')"

class Provider(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Información básica
    name = db.Column(db.String(150), nullable=False, unique=True)
    provider_type = db.Column(db.String(50), nullable=False, default='Bienes', index=True) # Bienes, Servicios
    tax_id = db.Column(db.String(20), unique=True, nullable=True) # Cédula fiscal / RIF
    address = db.Column(db.Text, nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    fax = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    # Contacto principal
    contact_person_name = db.Column(db.String(100), nullable=True)
    contact_person_phone = db.Column(db.String(50), nullable=True)
    contact_person_email = db.Column(db.String(120), nullable=True)
    # Información bancaria
    bank_name = db.Column(db.String(100), nullable=True)
    bank_branch = db.Column(db.String(100), nullable=True)
    bank_account_number = db.Column(db.String(30), nullable=True)
    bank_account_currency = db.Column(db.String(10), nullable=True)
    bank_swift_bic = db.Column(db.String(20), nullable=True)
    bank_iban = db.Column(db.String(34), nullable=True)
    # Detalles del negocio y términos
    business_description = db.Column(db.Text, nullable=True)
    payment_terms = db.Column(db.Text, nullable=True)
    shipping_terms = db.Column(db.Text, nullable=True)

    
    # Relaciones
    purchases = db.relationship('Purchase', backref='provider', lazy=True)
    service_orders = db.relationship('MarketingServiceOrder', backref='provider', lazy='dynamic')
    client_association = db.relationship('Client', backref=db.backref('associated_provider', uselist=False), foreign_keys=[Client.provider_id])

    def __repr__(self):
        return f"Provider('{self.name}')"

    def get_balance_usd(self):
        """
        Calcula el saldo actual del proveedor.
        Saldo a favor (positivo): Crédito que la tienda tiene con el proveedor.
        Saldo en contra (negativo): Deuda que la tienda tiene con el proveedor.
        """
        # Suma de todos los servicios que el proveedor ha prestado (crédito para la tienda)
        total_services_value = db.session.query(func.sum(MarketingServiceOrder.service_value_usd)) \
            .filter_by(provider_id=self.id, status='Completado').scalar() or 0.0

        # CORRECCIÓN: Sumar todos los pagos que consumen el saldo del proveedor.
        # Esto incluye tanto 'cruce_de_cuentas' (método antiguo/otro) como 'intercambio_comercial' (usado en el modal de pagos).
        # El 'provider_id' se guarda en el campo 'reference' para estos tipos de pago.
        total_settlements_value = db.session.query(func.sum(Payment.amount_usd_equivalent)) \
            .filter(Payment.reference == str(self.id)) \
            .filter(Payment.method.in_(['cruce_de_cuentas', 'intercambio_comercial'])) \
            .scalar() or 0.0

        return total_services_value - total_settlements_value
    
class MarketingServiceOrder(db.Model):
    __tablename__ = 'marketing_service_orders'
    id = db.Column(db.Integer, primary_key=True)
    service_code = db.Column(db.String(50), unique=True, nullable=False)
    provider_id = db.Column(db.Integer, db.ForeignKey('provider.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.DateTime(timezone=True), nullable=False, default=get_current_time_ve)
    service_description = db.Column(db.Text, nullable=False)
    service_value_usd = db.Column(db.Float, nullable=False, default=0.0) # Valor del servicio que genera crédito
    status = db.Column(db.String(50), nullable=False, default='Pendiente', index=True) # Pendiente, Completado, Cancelado

    # Relationships
    user = db.relationship('User', backref='service_orders_created')

    def __repr__(self):
        return f"MarketingServiceOrder('{self.service_code}', '{self.status}')"

class Order(db.Model):
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    date_created = db.Column(db.DateTime(timezone=True), nullable=False, default=get_current_time_ve)
    order_type = db.Column(db.String(20), nullable=False, default='regular')
    status = db.Column(db.String(20), nullable=False, default='Pendiente')
    total_amount = db.Column(db.Float, nullable=False, default=0.0)
    total_amount_usd = db.Column(db.Float, nullable=False, default=0.0) # Total en USD al momento de la venta
    discount_usd = db.Column(db.Float, nullable=True, default=0.0)
    exchange_rate_at_sale = db.Column(db.Float, nullable=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=True, index=True) # Puede ser nulo para órdenes antiguas
    dispatch_reason = db.Column(db.Text, nullable=True)

    # Relaciones
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade="all, delete-orphan")
    payments = db.relationship('Payment', backref='order', lazy=True, cascade="all, delete-orphan")
    

    @property
    def paid_amount_usd(self):
        """Calculates the total paid amount for this order in USD."""
        total_paid_usd = 0
        # Use a generator expression with sum() and handle None values
        return sum(p.amount_usd_equivalent or 0.0 for p in self.payments)

    @property
    def paid_amount(self):
        """Calcula el monto total pagado para esta orden en VES."""
        # Handle possible None values for consistency
        return sum(p.amount_ves_equivalent or 0.0 for p in self.payments)

    @property
    def due_amount(self):
        """
        Calcula el monto adeudado para esta orden en VES.
        Para créditos y apartados, el saldo en USD se convierte a VES con la tasa actual.
        """
        from .routes import get_cached_exchange_rate # Importación local para evitar dependencia circular
        
        due_usd = self.due_amount_usd
        if due_usd > 0:
            current_rate = get_cached_exchange_rate('USD') or self.exchange_rate_at_sale or 1
            return due_usd * current_rate
        
        return 0.0

    @property
    def due_amount_usd(self):
        """Calcula el monto adeudado para esta orden en USD."""
        # Se usa 'or 0.0' para manejar órdenes antiguas que puedan tener total_amount_usd como None
        total_usd = self.total_amount_usd or 0.0
        due = total_usd - self.paid_amount_usd
        return due if due > 0.01 else 0.0

    def __repr__(self):
        return f"Order('{self.id}', '{self.total_amount}')"

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.BigInteger, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False) # Precio en VES en el momento de la venta
    cost_at_sale_ves = db.Column(db.Float, nullable=True) # Costo unitario en VES en el momento de la venta
    returned_quantity = db.Column(db.Integer, nullable=False, default=0)

    def __repr__(self):
        return f"OrderItem('{self.order_id}', '{self.product_id}', '{self.quantity}')"

class OrderReturn(db.Model):
    __tablename__ = 'order_returns'
    id = db.Column(db.Integer, primary_key=True)
    return_code = db.Column(db.String(50), unique=True, nullable=False)
    order_id = db.Column(db.BigInteger, db.ForeignKey('order.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.DateTime(timezone=True), nullable=False, default=get_current_time_ve)
    return_type = db.Column(db.String(50), nullable=False) # 'Anulación Total', 'Devolución Parcial'
    reason = db.Column(db.String(255), nullable=False)
    total_refund_value_ves = db.Column(db.Float, nullable=False, default=0.0)

    # Relationships
    order = db.relationship('Order', backref=db.backref('returns', lazy='dynamic'))
    user = db.relationship('User', backref=db.backref('processed_returns', lazy='dynamic'))
    items = db.relationship('OrderReturnItem', backref='order_return', lazy=True, cascade="all, delete-orphan")
    # Relación con los movimientos financieros de reembolso
    refund_movements = db.relationship('ManualFinancialMovement', backref='order_return', lazy='dynamic')

class OrderReturnItem(db.Model):
    __tablename__ = 'order_return_items'
    id = db.Column(db.Integer, primary_key=True)
    order_return_id = db.Column(db.Integer, db.ForeignKey('order_returns.id'), nullable=False)
    order_item_id = db.Column(db.Integer, db.ForeignKey('order_item.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False) # Cantidad devuelta en esta transacción
    price_at_return_ves = db.Column(db.Float, nullable=False)

    # Relationship to Product
    product = db.relationship('Product')

class Bank(db.Model):
    __tablename__ = 'banks'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    code = db.Column(db.String(10), nullable=True, unique=True) # Código único del banco (ej: 0134 para Banesco)
    account_number = db.Column(db.String(20), nullable=True, unique=True)
    balance = db.Column(db.Float, nullable=False, default=0.0) # Balance in the bank's currency
    currency = db.Column(db.String(3), nullable=False, default='VES') # 'VES', 'USD', etc.
    
    payments = db.relationship('Payment', backref='bank', lazy=True)
    pos_terminals = db.relationship('PointOfSale', backref='bank', lazy=True)

    def __repr__(self):
        return f"Bank('{self.name}', '{self.currency}')"

class PointOfSale(db.Model):
    __tablename__ = 'points_of_sale'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    bank_id = db.Column(db.Integer, db.ForeignKey('banks.id'), nullable=False)
    
    payments = db.relationship('Payment', backref='pos', lazy=True)

    def __repr__(self):
        return f"PointOfSale('{self.name}')"

class CashBox(db.Model):
    __tablename__ = 'cash_boxes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    balance_ves = db.Column(db.Float, nullable=False, default=0.0)
    balance_usd = db.Column(db.Float, nullable=False, default=0.0)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False, index=True)
    
    payments = db.relationship('Payment', backref='cash_box', lazy=True)

    # Relación con Sucursal
    store = db.relationship('Store', backref=db.backref('cash_boxes', lazy='dynamic'))
    
    def __repr__(self):
        return f"CashBox('{self.name}')"

class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.BigInteger, db.ForeignKey('order.id'), nullable=False)
    amount_paid = db.Column(db.Float, nullable=False) # The amount in the currency it was paid
    currency_paid = db.Column(db.String(3), nullable=False) # 'VES', 'USD'
    amount_ves_equivalent = db.Column(db.Float, nullable=False) # The equivalent in VES for the order total
    amount_usd_equivalent = db.Column(db.Float, nullable=False, default=0.0) # El equivalente en USD para el total de la orden
    method = db.Column(db.String(50), nullable=False) # 'transferencia', 'pago_movil', 'punto_de_venta', 'efectivo_usd', 'efectivo_ves', 'cruce_de_cuentas'
    reference = db.Column(db.String(100), nullable=True)
    issuing_bank = db.Column(db.String(100), nullable=True) # Banco emisor
    sender_id = db.Column(db.String(50), nullable=True) # Cédula o teléfono del emisor
    date = db.Column(db.DateTime(timezone=True), nullable=False, default=get_current_time_ve)
    
    exchange_rate_at_payment = db.Column(db.Float, nullable=True) # NEW: Rate used for this specific payment
    # Destination of funds
    bank_id = db.Column(db.Integer, db.ForeignKey('banks.id'), nullable=True)
    pos_id = db.Column(db.Integer, db.ForeignKey('points_of_sale.id'), nullable=True)
    cash_box_id = db.Column(db.Integer, db.ForeignKey('cash_boxes.id'), nullable=True)

    def __repr__(self):
        return f"Payment('{self.id}', '{self.method}', '{self.amount_ves_equivalent}')"

class ManualFinancialMovement(db.Model):
    __tablename__ = 'manual_financial_movements'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime(timezone=True), nullable=False, default=get_current_time_ve)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), nullable=False) # 'VES', 'USD'
    movement_type = db.Column(db.String(20), nullable=False) # 'Ingreso', 'Egreso'
    received_by = db.Column(db.String(100), nullable=True) # Who received the money
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Aprobado', index=True) # Pendiente, Aprobado, Rechazado
    approved_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    date_approved = db.Column(db.DateTime(timezone=True), nullable=True)

    # Foreign keys to the accounts
    bank_id = db.Column(db.Integer, db.ForeignKey('banks.id'), nullable=True)
    cash_box_id = db.Column(db.Integer, db.ForeignKey('cash_boxes.id'), nullable=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchase.id'), nullable=True, index=True)
    order_return_id = db.Column(db.Integer, db.ForeignKey('order_returns.id'), nullable=True, index=True)
    
    # Relationships
    bank = db.relationship('Bank', backref=db.backref('manual_movements', lazy='dynamic'))
    cash_box = db.relationship('CashBox', backref=db.backref('manual_movements', lazy='dynamic'))
    created_by_user = db.relationship('User', backref=db.backref('financial_movements_created', lazy='dynamic'), foreign_keys=[created_by_user_id])
    approved_by_user = db.relationship('User', backref=db.backref('financial_movements_approved', lazy='dynamic'), foreign_keys=[approved_by_user_id])
    purchase = db.relationship('Purchase', backref=db.backref('payments', lazy='dynamic'))

    def __repr__(self):
        return f"ManualFinancialMovement('{self.description}', '{self.amount} {self.currency}')"

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey('provider.id'), nullable=False)
    date_created = db.Column(db.DateTime(timezone=True), nullable=False, default=get_current_time_ve)
    status = db.Column(db.String(20), nullable=False, default='Pendiente')
    payment_status = db.Column(db.String(20), nullable=False, default='Pendiente de Pago')
    total_cost = db.Column(db.Float, nullable=False, default=0.0)

    # Relaciones
    items = db.relationship('PurchaseItem', backref='purchase', lazy=True)
    receptions = db.relationship('Reception', backref='purchase', lazy=True)
    
    def __repr__(self):
        return f"Purchase('{self.id}', '{self.total_cost}')"

class PurchaseItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchase.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    cost = db.Column(db.Float, nullable=False) # Costo en VES en el momento de la compra
    quantity_received = db.Column(db.Integer, nullable=False, default=0)

    @property
    def quantity_pending(self):
        """Returns the quantity of this item that is yet to be received."""
        pending = self.quantity - self.quantity_received
        return pending if pending > 0 else 0
        
    def __repr__(self):
        return f"PurchaseItem('{self.purchase_id}', '{self.product_id}', '{self.quantity}')"

class Reception(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchase.id'), nullable=False)
    date_received = db.Column(db.DateTime(timezone=True), nullable=False, default=get_current_time_ve)
    status = db.Column(db.String(20), nullable=False, default='Pendiente')

    def __repr__(self):
        return f"Reception('{self.id}', '{self.purchase_id}')"

class Movement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'Entrada', 'Salida'
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouse.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False) 
    date = db.Column(db.DateTime(timezone=True), nullable=False, default=get_current_time_ve)
    document_id = db.Column(db.BigInteger, nullable=True) # ID de la orden, compra, etc.
    document_type = db.Column(db.String(50), nullable=True) # 'Orden de Venta', 'Orden de Compra', 'Ajuste'
    description = db.Column(db.String(255), nullable=True) # Para comentarios de ajuste, etc.
    comment = db.Column(db.String(255), nullable=True) # Comentario específico del item en el movimiento
    related_party_id = db.Column(db.Integer, nullable=True) # ID del cliente o proveedor
    related_party_type = db.Column(db.String(50), nullable=True) # 'Cliente', 'Proveedor'
    
    warehouse = db.relationship('Warehouse', backref='movements')

    def __repr__(self):
        return f"Movement('{self.type}', '{self.product_id}', '{self.quantity}')"

class ProductStock(db.Model):
    __tablename__ = 'product_stock'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouse.id'), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False, default=0)

    warehouse = db.relationship('Warehouse', backref='stock_levels')
    __table_args__ = (db.UniqueConstraint('product_id', 'warehouse_id', name='_product_warehouse_uc'),)

class WarehouseTransfer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transfer_code = db.Column(db.String(50), unique=True, nullable=True)
    date = db.Column(db.DateTime(timezone=True), nullable=False, default=get_current_time_ve)
    reason = db.Column(db.String(255), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('User', backref='warehouse_transfers')

class InventoryAdjustment(db.Model):
    __tablename__ = 'inventory_adjustments'
    id = db.Column(db.Integer, primary_key=True)
    adjustment_code = db.Column(db.String(50), unique=True, nullable=True) # e.g., INV18070001
    date = db.Column(db.DateTime(timezone=True), nullable=False, default=get_current_time_ve)
    reason = db.Column(db.String(255), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Summary fields
    value_difference_usd = db.Column(db.Float, nullable=False, default=0.0)
    
    # Relationships
    items = db.relationship('InventoryAdjustmentItem', backref='adjustment', lazy=True, cascade="all, delete-orphan")
    user = db.relationship('User', backref='inventory_adjustments')

class BulkLoadLog(db.Model):
    __tablename__ = 'bulk_load_logs'
    id = db.Column(db.Integer, primary_key=True)
    adjustment_code = db.Column(db.String(50), unique=True, nullable=True) # e.g., INV18070001
    date = db.Column(db.DateTime(timezone=True), nullable=False, default=get_current_time_ve)
    reason = db.Column(db.String(255), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    method = db.Column(db.String(50), nullable=False, default='Excel') # 'Excel', 'API', etc.
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouse.id'), nullable=False)

    user = db.relationship('User', backref='bulk_loads')
    warehouse = db.relationship('Warehouse', backref='bulk_loads')
    
    from sqlalchemy.orm import foreign

    # Relationship to Movement
    movements = db.relationship(
        'Movement',
        primaryjoin="and_(foreign(Movement.document_id) == BulkLoadLog.id, "
                    "foreign(Movement.document_type).like('Carga Masiva%'))",
        backref='bulk_load_log',
        lazy='dynamic'
    )

class InventoryAdjustmentItem(db.Model):
    __tablename__ = 'inventory_adjustment_items'
    id = db.Column(db.Integer, primary_key=True)
    adjustment_id = db.Column(db.Integer, db.ForeignKey('inventory_adjustments.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    theoretical_stock = db.Column(db.Integer, nullable=False)
    real_stock = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.String(255), nullable=True)
    cost_at_adjustment_usd = db.Column(db.Float, nullable=False)
    product = db.relationship('Product')

class CompanyInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    rif = db.Column(db.String(20), unique=True, nullable=False)
    address = db.Column(db.String(200), nullable=True)
    phone_numbers = db.Column(db.String(100), nullable=True)
    logo_filename = db.Column(db.String(200), nullable=True)
    calculation_currency = db.Column(db.String(3), nullable=False, default='USD')

    def __repr__(self):
        return f"CompanyInfo('{self.name}', '{self.rif}')"

class ExchangeRate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    currency = db.Column(db.String(3), unique=True, nullable=False)
    rate = db.Column(db.Float, nullable=False)
    date_updated = db.Column(db.DateTime(timezone=True), nullable=False, default=get_current_time_ve)

    def __repr__(self):
        return f"ExchangeRate(currency='{self.currency}', rate='{self.rate}', date='{self.date_updated}')"

class HistoricalExchangeRate(db.Model):
    __tablename__ = 'historical_exchange_rates'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False) # Store only date
    currency = db.Column(db.String(3), nullable=False, default='USD') # To support other currencies if needed, but default to USD
    rate = db.Column(db.Float, nullable=False)
    date_recorded = db.Column(db.DateTime(timezone=True), nullable=False, default=get_current_time_ve) # When this historical rate was recorded

    def __repr__(self):
        return f"HistoricalExchangeRate(date='{self.date}', currency='{self.currency}', rate='{self.rate}')"

class CostStructure(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    monthly_rent = db.Column(db.Float, default=0)
    monthly_utilities = db.Column(db.Float, default=0)
    monthly_fixed_taxes = db.Column(db.Float, default=0)
    default_sales_commission_percent = db.Column(db.Float, default=0.05) # 5% por defecto
    default_marketing_percent = db.Column(db.Float, default=0.03) # 3% por defecto

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    link = db.Column(db.String(255), nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=get_current_time_ve)

    user = db.relationship('User', backref=db.backref('notifications', lazy='dynamic'))

    def __repr__(self):
        return f"Notification('{self.message}', '{self.is_read}')"

class UserActivityLog(db.Model):
    __tablename__ = 'user_activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=get_current_time_ve)
    action = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text, nullable=True)
    target_id = db.Column(db.String(50), nullable=True) # String to accommodate codes like AIV23...
    target_type = db.Column(db.String(50), nullable=True)

    user = db.relationship('User', backref=db.backref('activity_logs', lazy='dynamic'))

    def __repr__(self):
        return f"UserActivityLog('{self.user.username}', '{self.action}', '{self.created_at}')"

class ClientCreditMovement(db.Model):
    __tablename__ = 'client_credit_movement'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    movement_type = db.Column(db.String(10), nullable=False)  # 'Ingreso' o 'Egreso'
    amount_usd = db.Column(db.Numeric(10, 2), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    related_order_id = db.Column(db.BigInteger, db.ForeignKey('order.id'), nullable=True)
    related_payment_id = db.Column(db.Integer, db.ForeignKey('payments.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.DateTime(timezone=True), default=get_current_time_ve, nullable=False)

    # Relaciones
    user = db.relationship('User', backref='client_credit_movements')
    order = db.relationship('Order', backref='client_credit_movements')
    payment = db.relationship('Payment', backref='client_credit_movement')

    def __repr__(self):
        return f"<ClientCreditMovement {self.id} - {self.movement_type} ${self.amount_usd}>"