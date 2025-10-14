from datetime import datetime
import pytz

# Define la zona horaria de Venezuela (GMT-4)
VE_TIMEZONE = pytz.timezone('America/Caracas')

def get_current_time_ve():
    """Retorna la hora actual en la zona horaria de Venezuela."""
    return datetime.now(VE_TIMEZONE)

from .extensions import db
from flask_login import UserMixin

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='empleado') # 'empleado', 'administrador'

    def __repr__(self):
        return f"User('{self.username}', '{self.role}')"

class UserDevice(db.Model):
    __tablename__ = 'user_devices'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    fcm_token = db.Column(db.String(255), unique=True, nullable=False)
    device_type = db.Column(db.String(50), nullable=True, default='android') # 'android', 'ios', 'web'
    last_login = db.Column(db.DateTime(timezone=True), default=get_current_time_ve, onupdate=get_current_time_ve)

    user = db.relationship('User', backref=db.backref('devices', lazy='dynamic', cascade="all, delete-orphan"))

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
    movements = db.relationship('Movement', backref='product', lazy=True)

    def __repr__(self):
        return f"Product('{self.name}', '{self.barcode}')"

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    cedula_rif = db.Column(db.String(40), nullable=True)
    email = db.Column(db.String(120), unique=False, nullable=True)
    phone = db.Column(db.String(40), nullable=True)
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
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    date_created = db.Column(db.DateTime(timezone=True), nullable=False, default=get_current_time_ve)
    order_type = db.Column(db.String(20), nullable=False, default='regular')
    status = db.Column(db.String(20), nullable=False, default='Pendiente')
    total_amount = db.Column(db.Float, nullable=False, default=0.0)
    total_amount_usd = db.Column(db.Float, nullable=False, default=0.0) # Total en USD al momento de la venta
    discount_usd = db.Column(db.Float, nullable=True, default=0.0)
    exchange_rate_at_sale = db.Column(db.Float, nullable=True)

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

    def __repr__(self):
        return f"OrderItem('{self.order_id}', '{self.product_id}', '{self.quantity}')"

class Bank(db.Model):
    __tablename__ = 'banks'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
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
    
    payments = db.relationship('Payment', backref='cash_box', lazy=True)

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
    method = db.Column(db.String(50), nullable=False) # 'transferencia', 'pago_movil', 'punto_de_venta', 'efectivo_usd', 'efectivo_ves'
    reference = db.Column(db.String(100), nullable=True)
    issuing_bank = db.Column(db.String(100), nullable=True) # Banco emisor
    sender_id = db.Column(db.String(50), nullable=True) # Cédula o teléfono del emisor
    date = db.Column(db.DateTime(timezone=True), nullable=False, default=get_current_time_ve)
    
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
    quantity = db.Column(db.Integer, nullable=False)
    date = db.Column(db.DateTime(timezone=True), nullable=False, default=get_current_time_ve)
    document_id = db.Column(db.BigInteger, nullable=True) # ID de la orden, compra, etc.
    document_type = db.Column(db.String(50), nullable=True) # 'Orden de Venta', 'Orden de Compra', 'Ajuste'
    description = db.Column(db.String(255), nullable=True) # Para comentarios de ajuste, etc.
    related_party_id = db.Column(db.Integer, nullable=True) # ID del cliente o proveedor
    related_party_type = db.Column(db.String(50), nullable=True) # 'Cliente', 'Proveedor'

    def __repr__(self):
        return f"Movement('{self.type}', '{self.product_id}', '{self.quantity}')"

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
