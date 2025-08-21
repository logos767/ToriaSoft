from flask import Blueprint, render_template, url_for, flash, redirect, request, jsonify, session, current_app
from flask_login import login_user, current_user, logout_user, login_required
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, extract
import openpyxl

# Import extensions from the new extensions file
from .extensions import db, bcrypt, socketio
from .models import User, Product, Client, Provider, Order, OrderItem, Purchase, PurchaseItem, Reception, Movement, CompanyInfo, CostStructure, Notification, ExchangeRate

routes_blueprint = Blueprint('main', __name__)



# Helper para obtener la tasa de cambio actual
def get_current_exchange_rate():
    """
    Obtiene la tasa de cambio más reciente desde la base de datos.
    Esta tasa es actualizada por una tarea en segundo plano.
    """
    try:
        # Usar .with_for_update() puede ser útil en escenarios de alta concurrencia, pero no es estrictamente necesario aquí.
        rate_entry = ExchangeRate.query.first()
        if rate_entry:
            return rate_entry.rate
    except Exception as e:
        current_app.logger.error(f"Error al obtener la tasa de cambio de la base de datos: {e}")
    return None

# --- Funciones del Sistema de Notificaciones ---

def create_notification_for_admins(message, link):
    """
    Crea una notificación para todos los usuarios con rol 'administrador'.
    """
    try:
        # Asume que el modelo User tiene un campo 'role'
        admins = User.query.filter_by(role='administrador').all()
        if not admins:
            return

        for admin in admins:
            notification = Notification(
                user_id=admin.id,
                message=message,
                link=link
            )
            db.session.add(notification)
            db.session.flush() # Para obtener los datos generados por la DB (como created_at)

            # Emitir evento de WebSocket a la sala específica del administrador
            socketio.emit('new_notification', {
                'message': notification.message,
                'link': notification.link,
                'created_at': notification.created_at.strftime('%d/%m %H:%M')
            }, room=f'user_{admin.id}')

    except Exception as e:
        # Usar logger para registrar el error sin detener el flujo principal
        current_app.logger.error(f"Error al crear notificaciones para administradores: {e}")
        db.session.rollback() # Revertir si algo falla

@routes_blueprint.context_processor
def inject_notifications():
    """
    Hace que las notificaciones no leídas estén disponibles en el contexto de la plantilla
    para los usuarios administradores.
    """
    if not current_user.is_authenticated or current_user.role != 'administrador':
        return dict(unread_notifications=[], unread_notification_count=0)
    
    try:
        unread_notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).order_by(Notification.created_at.desc()).limit(10).all()
        count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        return dict(
            unread_notifications=unread_notifications,
            unread_notification_count=count
        )
    except Exception as e:
        current_app.logger.error(f"Error al obtener notificaciones para el usuario {current_user.id}: {e}")
        return dict(unread_notifications=[], unread_notification_count=0)

@routes_blueprint.route('/notifications/mark-as-read', methods=['POST'])
@login_required
def mark_notifications_as_read():
    if current_user.role != 'administrador':
        return jsonify(success=False, message='Acceso denegado'), 403
    try:
        Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
        db.session.commit()
        return jsonify(success=True)
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al marcar notificaciones como leídas para el usuario {current_user.id}: {e}")
        return jsonify(success=False, message='Error interno del servidor'), 500

@socketio.on('connect')
def handle_connect():
    """
    Cuando un usuario se conecta, lo une a una sala con su ID.
    Esto permite enviarle notificaciones de forma privada.
    """
    if current_user.is_authenticated:
        join_room(f'user_{current_user.id}')

# Rutas de autenticación
@routes_blueprint.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('main.dashboard'))
        else:
            flash('Inicio de sesión fallido. Por favor, verifica tu nombre de usuario y contraseña.', 'danger')
    return render_template('login.html', title='Iniciar Sesión')


@routes_blueprint.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.login'))

# Rutas principales
@routes_blueprint.route('/')
@routes_blueprint.route('/dashboard')
@login_required
def dashboard():
    """Muestra la página principal con información de dashboard."""
    total_products = Product.query.count()
    total_stock = db.session.query(db.func.sum(Product.stock)).scalar() or 0
    total_clients = Client.query.count()
    total_orders = Order.query.count()
    
    # Obtener la tasa y usar 0.0 como valor por defecto solo para visualización
    current_rate = get_current_exchange_rate() or 0.0

    # Puedes agregar más métricas relevantes aquí
    recent_products = Product.query.order_by(Product.id.desc()).limit(5).all()
    recent_orders = Order.query.order_by(Order.date_created.desc()).limit(5).all()

    return render_template('index.html', title='Dashboard',
                           total_products=total_products,
                           total_stock=total_stock,
                           total_clients=total_clients,
                           total_orders=total_orders,
                           recent_products=recent_products,
                           recent_orders=recent_orders,
                           current_rate=current_rate)

# Rutas de productos (Inventario)
@routes_blueprint.route('/inventario/lista')
@login_required
def inventory_list():
    """
    Muestra la lista de productos en el inventario,
    con vistas de lista (tabla) y cuadrícula.
    """
    products = Product.query.all()
    user_role = current_user.role if current_user.is_authenticated else 'invitado'
    current_rate = get_current_exchange_rate() or 0.0
    return render_template('inventario/lista.html',
                           title='Lista de Inventario',
                           products=products,
                           user_role=user_role,
                           current_rate=current_rate)

@routes_blueprint.route('/inventario/existencias')
@login_required
def inventory_stock():
    """Muestra el estado de existencias de los productos."""
    products = Product.query.all()
    current_rate = get_current_exchange_rate() or 0.0
    return render_template('inventario/existencias.html', title='Existencias', products=products, current_rate=current_rate)

@routes_blueprint.route('/inventario/producto/<int:product_id>')
@login_required
def product_detail(product_id):
    """Muestra los detalles de un producto específico, incluyendo código de barras y QR."""
    product = Product.query.get_or_404(product_id)
    current_rate = get_current_exchange_rate() or 0.0
    return render_template('inventario/detalle_producto.html', title=product.name, product=product, current_rate=current_rate)

@routes_blueprint.route('/inventario/nuevo', methods=['GET', 'POST'])
@login_required
def new_product():
    """Maneja el formulario para crear un nuevo producto."""
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            description = request.form.get('description')
            barcode = request.form.get('barcode')
            qr_code = request.form.get('qr_code')
            image_url = request.form.get('image_url')
            size = request.form.get('size')
            color = request.form.get('color')
            cost_usd = float(request.form.get('cost_usd'))
            price_usd = float(request.form.get('price_usd'))

            new_prod = Product(
                name=name, description=description, barcode=barcode, qr_code=qr_code,
                image_url=image_url, size=size, color=color, cost_usd=cost_usd, price_usd=price_usd, stock=0
            )
            db.session.add(new_prod)
            db.session.commit()
            flash('Producto creado exitosamente!', 'success')
            return redirect(url_for('main.inventory_list'))
        except (ValueError, IntegrityError) as e:
            db.session.rollback()
            flash(f'Error al crear el producto: {str(e)}', 'danger')
    return render_template('inventario/nuevo.html', title='Nuevo Producto', current_rate=get_current_exchange_rate() or 0.0)

# Rutas de clientes
@routes_blueprint.route('/clientes/lista')
@login_required
def client_list():
    """Muestra la lista de clientes."""
    clients = Client.query.all()
    current_rate = get_current_exchange_rate() or 0.0
    return render_template('clientes/lista.html', title='Lista de Clientes', clients=clients, current_rate=current_rate)

@routes_blueprint.route('/clientes/nuevo', methods=['GET', 'POST'])
@login_required
def new_client():
    """Maneja el formulario para crear un nuevo cliente."""
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            email = request.form.get('email')
            phone = request.form.get('phone')
            address = request.form.get('address')
            new_cli = Client(name=name, email=email, phone=phone, address=address)
            db.session.add(new_cli)
            db.session.commit()
            flash('Cliente creado exitosamente!', 'success')
            return redirect(url_for('main.client_list'))
        except IntegrityError:
            db.session.rollback()
            flash('Error: El email ya está registrado.', 'danger')
    return render_template('clientes/nuevo.html', title='Nuevo Cliente', current_rate=get_current_exchange_rate() or 0.0)

# Rutas de proveedores
@routes_blueprint.route('/proveedores/lista')
@login_required
def provider_list():
    """Muestra la lista de proveedores."""
    providers = Provider.query.all()
    current_rate = get_current_exchange_rate() or 0.0
    return render_template('proveedores/lista.html', title='Lista de Proveedores', providers=providers, current_rate=current_rate)

@routes_blueprint.route('/proveedores/nuevo', methods=['GET', 'POST'])
@login_required
def new_provider():
    """Maneja el formulario para crear un nuevo proveedor."""
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            contact = request.form.get('contact')
            phone = request.form.get('phone')
            new_prov = Provider(name=name, contact=contact, phone=phone)
            db.session.add(new_prov)
            db.session.commit()
            flash('Proveedor creado exitosamente!', 'success')
            return redirect(url_for('main.provider_list'))
        except IntegrityError:
            db.session.rollback()
            flash('Error: Hubo un problema al crear el proveedor.', 'danger')
    return render_template('proveedores/nuevo.html', title='Nuevo Proveedor', current_rate=get_current_exchange_rate() or 0.0)

# Rutas de compras
@routes_blueprint.route('/compras/lista')
@login_required
def purchase_list():
    """Muestra la lista de compras."""
    purchases = Purchase.query.all()
    current_rate = get_current_exchange_rate() or 0.0
    return render_template('compras/lista.html', title='Lista de Compras', purchases=purchases, current_rate=current_rate)

@routes_blueprint.route('/compras/detalle/<int:purchase_id>')
@login_required
def purchase_detail(purchase_id):
    """Muestra los detalles de una compra específica."""
    purchase = Purchase.query.get_or_404(purchase_id)
    current_rate = get_current_exchange_rate() or 0.0
    return render_template('compras/detalle_compra.html', title=f'Compra #{purchase.id}', purchase=purchase, current_rate=current_rate)

@routes_blueprint.route('/compras/nuevo', methods=['GET', 'POST'])
@login_required
def new_purchase():
    """Maneja el formulario para crear una nueva compra."""
    providers = Provider.query.all()
    products = Product.query.all()
    current_rate = get_current_exchange_rate()

    if current_rate is None:
        flash('No se ha podido obtener la tasa de cambio. No se pueden crear compras en este momento.', 'danger')
        return redirect(url_for('main.purchase_list'))

    if request.method == 'POST':
        try:
            provider_id = request.form.get('provider_id')
            total_cost = 0
            
            new_purchase = Purchase(provider_id=provider_id, total_cost=total_cost)
            db.session.add(new_purchase)
            db.session.commit()
            
            # Procesar los productos de la compra
            product_ids = request.form.getlist('product_id[]')
            quantities = request.form.getlist('quantity[]')
            costs_usd = request.form.getlist('cost_usd[]')

            for p_id, q, c_usd in zip(product_ids, quantities, costs_usd):
                product = Product.query.get(p_id)
                if product and int(q) > 0:
                    # Guardar el costo en VES al momento de la compra
                    cost_ves = float(c_usd) * current_rate
                    item = PurchaseItem(
                        purchase_id=new_purchase.id,
                        product_id=p_id,
                        quantity=int(q),
                        cost=cost_ves
                    )
                    db.session.add(item)
                    total_cost += cost_ves * int(q)
            
            new_purchase.total_cost = total_cost
            
            # Crear notificación para administradores
            notification_message = f"Nueva Orden de Compra #{new_purchase.id} creada."
            notification_link = url_for('main.purchase_detail', purchase_id=new_purchase.id)
            create_notification_for_admins(notification_message, notification_link)

            db.session.commit()

            flash('Compra creada exitosamente!', 'success')
            return redirect(url_for('main.purchase_list'))
        except (ValueError, IntegrityError) as e:
            db.session.rollback()
            flash(f'Error al crear la compra: {str(e)}', 'danger')
    
    return render_template('compras/nuevo.html', title='Nueva Compra', providers=providers, products=products, current_rate=current_rate)

# Rutas de recepciones
@routes_blueprint.route('/recepciones/lista')
@login_required
def reception_list():
    """Muestra la lista de recepciones."""
    receptions = Reception.query.all()
    current_rate = get_current_exchange_rate() or 0.0
    return render_template('recepciones/lista.html', title='Lista de Recepciones', receptions=receptions, current_rate=current_rate)

@routes_blueprint.route('/recepciones/nueva/<int:purchase_id>', methods=['GET', 'POST'])
@login_required
def new_reception(purchase_id):
    """Maneja el formulario para una nueva recepción y actualiza el stock."""
    purchase = Purchase.query.get_or_404(purchase_id)
    current_rate = get_current_exchange_rate() or 0.0
    if request.method == 'POST':
        try:
            new_reception = Reception(purchase_id=purchase.id, status='Completada')
            db.session.add(new_reception)

            for item in purchase.items:
                product = Product.query.get(item.product_id)
                if product:
                    product.stock += item.quantity
                    db.session.add(product)
                    
                    # Log del movimiento de entrada
                    movement = Movement(
                        product_id=product.id,
                        type='Entrada',
                        quantity=item.quantity,
                        document_id=purchase.id,
                        document_type='Orden de Compra',
                        related_party_id=purchase.provider_id,
                        related_party_type='Proveedor'
                    )
                    db.session.add(movement)
            
            # Crear notificación para administradores
            notification_message = f"Nueva recepción para la compra #{purchase.id} procesada."
            # No hay una vista de detalle para la recepción, así que enlazamos a la lista.
            notification_link = url_for('main.reception_list')
            create_notification_for_admins(notification_message, notification_link)

            db.session.commit()
            flash('Recepción completada y stock actualizado!', 'success')
            return redirect(url_for('main.reception_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al procesar la recepción: {str(e)}', 'danger')

    return render_template('recepciones/nueva.html', title='Nueva Recepción', purchase=purchase, current_rate=current_rate)


# Rutas de órdenes
@routes_blueprint.route('/ordenes/lista')
@login_required
def order_list():
    """Muestra la lista de órdenes."""
    orders = Order.query.all()
    current_rate = get_current_exchange_rate() or 0.0
    return render_template('ordenes/lista.html', title='Lista de Órdenes', orders=orders, current_rate=current_rate)

@routes_blueprint.route('/ordenes/detalle/<int:order_id>')
@login_required
def order_detail(order_id):
    """
    Muestra los detalles de una orden de venta específica.
    Ahora también busca la información de la empresa para mostrar el botón de impresión.
    """
    order = Order.query.get_or_404(order_id)
    company_info = CompanyInfo.query.first()
    current_rate = get_current_exchange_rate() or 0.0
    return render_template('ordenes/detalle_orden.html', 
                           title=f'Orden #{order.id}', 
                           order=order,
                           company_info=company_info,
                           current_rate=current_rate)

@routes_blueprint.route('/ordenes/nuevo', methods=['GET', 'POST'])
@login_required
def new_order():
    """Maneja el formulario para crear una nueva orden de venta."""
    clients = Client.query.all()
    products = Product.query.all()
    current_rate = get_current_exchange_rate()
    
    if current_rate is None:
        flash('No se ha podido obtener la tasa de cambio. No se pueden crear órdenes en este momento.', 'danger')
        return redirect(url_for('main.order_list'))
    
    if request.method == 'POST':
        try:
            client_id = request.form.get('client_id')
            total_amount = 0
            
            # Verificar el stock de cada producto antes de crear la orden
            product_ids = request.form.getlist('product_id[]')
            quantities = request.form.getlist('quantity[]')
            
            for p_id, q in zip(product_ids, quantities):
                product = Product.query.get(p_id)
                quantity = int(q)
                if product and quantity > 0:
                    if product.stock < quantity:
                        raise ValueError(f'Stock insuficiente para el producto: {product.name}')

            # Si todas las verificaciones de stock son exitosas, se procede a crear la orden
            new_order = Order(client_id=client_id, status='Pendiente', total_amount=total_amount)
            db.session.add(new_order)
            db.session.commit()

            # Procesar los productos de la orden y actualizar el stock
            prices_usd = request.form.getlist('price_usd[]')

            for p_id, q, p_usd in zip(product_ids, quantities, prices_usd):
                product = Product.query.get(p_id)
                quantity = int(q)
                
                # Guardar el precio en VES al momento de la venta
                price_ves = float(p_usd) * current_rate
                
                item = OrderItem(
                    order_id=new_order.id,
                    product_id=p_id,
                    quantity=quantity,
                    price=price_ves
                )
                db.session.add(item)
                total_amount += price_ves * quantity
                
                # Descontar del stock
                product.stock -= quantity
                db.session.add(product)
                
                # Log del movimiento de salida
                movement = Movement(
                    product_id=product.id,
                    type='Salida',
                    quantity=quantity,
                    document_id=new_order.id,
                    document_type='Orden de Venta',
                    related_party_id=new_order.client_id,
                    related_party_type='Cliente'
                )
                db.session.add(movement)
            
            new_order.total_amount = total_amount
            new_order.status = 'Completada'

            # Crear notificación para administradores (Nota de Entrega)
            notification_message = f"Nueva Nota de Entrega #{new_order.id} creada."
            notification_link = url_for('main.order_detail', order_id=new_order.id)
            create_notification_for_admins(notification_message, notification_link)

            db.session.commit()

            flash('Orden de venta creada exitosamente!', 'success')
            return redirect(url_for('main.order_list'))
        except (ValueError, IntegrityError) as e:
            db.session.rollback()
            flash(f'Error al crear la orden: {str(e)}', 'danger')
            return redirect(url_for('main.new_order'))

    return render_template('ordenes/nuevo.html', title='Nueva Orden de Venta', clients=clients, products=products, current_rate=current_rate)


# Nueva ruta para movimientos de inventario
@routes_blueprint.route('/movimientos/lista')
@login_required
def movement_list():
    """Muestra la lista de movimientos de inventario."""
    movements = Movement.query.order_by(Movement.date.desc()).all()
    current_rate = get_current_exchange_rate() or 0.0
    return render_template('movimientos/lista.html', title='Registro de Movimientos', movements=movements, current_rate=current_rate)


# Nueva ruta para estadísticas (modo gerencial)
@routes_blueprint.route('/estadisticas')
@login_required
def estadisticas():
    """Muestra las estadísticas y métricas del negocio con gráficos."""
    
    # 1. Productos más vendidos
    # Obtiene los productos con más cantidad vendida, incluyendo los que no tienen ventas.
    top_products = db.session.query(
        Product.name,
        func.sum(func.coalesce(OrderItem.quantity, 0)).label('total_sold')
    ).outerjoin(OrderItem).group_by(Product.id).order_by(func.sum(func.coalesce(OrderItem.quantity, 0)).desc()).limit(5).all()

    # 2. Productos menos vendidos (con ventas > 0)
    # Excluye productos sin ventas para una métrica más precisa de "menos vendidos"
    least_products = db.session.query(
        Product.name,
        func.sum(OrderItem.quantity).label('total_sold')
    ).join(OrderItem).group_by(Product.id).order_by('total_sold').limit(5).all()

    # 3. Clientes más frecuentes (por número de órdenes)
    frequent_clients = db.session.query(
        Client.name,
        func.count(Order.id).label('total_orders')
    ).outerjoin(Order).group_by(Client.id).order_by(func.count(Order.id).desc()).limit(5).all()

    # 4. Ventas por mes
    # Obtiene el monto total de ventas por cada mes del año actual.
    sales_by_month = db.session.query(
        extract('month', Order.date_created).label('month'),
        func.sum(Order.total_amount).label('total_sales')
    ).filter(extract('year', Order.date_created) == extract('year', func.now())).group_by('month').order_by('month').all()

    # Convierte los resultados a formatos más fáciles de usar en JS
    top_products_data = {'labels': [p[0] for p in top_products], 'values': [p[1] for p in top_products]}
    least_products_data = {'labels': [p[0] for p in least_products], 'values': [p[1] for p in least_products]}
    frequent_clients_data = {'labels': [c[0] for c in frequent_clients], 'values': [c[1] for c in frequent_clients]}
    
    # Prepara los datos de ventas mensuales (asegura que todos los meses estén presentes)
    months_names = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    monthly_sales = {int(s[0]): s[1] for s in sales_by_month}
    sales_data_complete = {'labels': months_names, 'values': [monthly_sales.get(i + 1, 0) for i in range(12)]}
    
    current_rate = get_current_exchange_rate() or 0.0

    return render_template('estadisticas.html',
                           title='Estadísticas Gerenciales',
                           top_products=top_products_data,
                           least_products=least_products_data,
                           frequent_clients=frequent_clients_data,
                           sales_by_month=sales_data_complete,
                           current_rate=current_rate)

# Nueva ruta para cargar productos desde un archivo de Excel
@routes_blueprint.route('/inventario/cargar_excel', methods=['GET', 'POST'])
@login_required
def cargar_excel():
    """
    Permite a los administradores cargar y actualizar productos desde un archivo de Excel.
    """
    if current_user.role != 'administrador':
        flash('Acceso denegado. Solo los administradores pueden realizar esta acción.', 'danger')
        return redirect(url_for('main.inventory_list'))

    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No se ha seleccionado ningún archivo.', 'danger')
            return redirect(request.url)

        file = request.files['file']
        if file.filename == '':
            flash('No se ha seleccionado ningún archivo.', 'danger')
            return redirect(request.url)
        
        # Validar la extensión del archivo
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash('Formato de archivo no válido. Solo se aceptan archivos .xlsx.', 'danger')
            return redirect(request.url)

        # Usar una ruta temporal para guardar el archivo
        filepath = os.path.join('/tmp', file.filename)
        file.save(filepath)

        try:
            # Abrir el archivo de Excel y seleccionar la hoja activa
            workbook = openpyxl.load_workbook(filepath)
            sheet = workbook.active
            
            # Dictionaries para almacenar productos nuevos y productos para actualizar
            new_products = []
            updates = []
            
            # Iterar sobre las filas, asumiendo que la primera fila son los encabezados
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if not row[0]:  # Si el código de barras está vacío, saltar la fila
                    continue
                
                # Asignar valores de las columnas (ajusta esto si tu formato de Excel cambia)
                # Formato de columnas esperado:
                # [0] Codigo, [1] Nombre, [2] Costo (USD), [3] Precio (USD), [4] Existencia, [5] Imagen
                barcode = str(row[0]).strip()
                name = str(row[1]).strip()
                cost_usd = row[2] if row[2] is not None else 0
                price_usd = row[3] if row[3] is not None else 0
                stock = row[4] if row[4] is not None else 0
                image_url = row[5] if row[5] is not None else ''

                # Buscar el producto en la base de datos por el código de barras
                product = Product.query.filter_by(barcode=barcode).first()

                if product:
                    # Producto existente, preparar para posible actualización
                    updates.append({
                        'id': product.id,
                        'name': product.name,
                        'new_stock': int(stock),
                        'old_stock': product.stock,
                        'new_cost_usd': float(cost_usd),
                        'old_cost_usd': product.cost_usd,
                        'new_name': name,
                        'new_price_usd': float(price_usd),
                        'new_image_url': image_url
                    })
                else:
                    # Nuevo producto, crear el objeto y agregarlo a la lista de nuevos
                    new_products.append(Product(
                        barcode=barcode,
                        name=name,
                        cost_usd=float(cost_usd),
                        price_usd=float(price_usd),
                        stock=int(stock),
                        image_url=image_url
                    ))

            # Guardar los productos nuevos en la base de datos
            if new_products:
                db.session.bulk_save_objects(new_products)
                flash(f'Se han agregado {len(new_products)} productos nuevos.', 'success')

            # Guardar las actualizaciones pendientes en la sesión para el paso de confirmación
            if updates:
                session['pending_updates'] = updates
                return redirect(url_for('main.cargar_excel_confirmar'))
            
            db.session.commit()
            flash('Archivo procesado exitosamente.', 'success')
            return redirect(url_for('main.inventory_list'))

        except Exception as e:
            db.session.rollback()
            flash(f'Ocurrió un error al procesar el archivo: {str(e)}', 'danger')
            return redirect(request.url)
        finally:
            # Eliminar el archivo temporal
            if os.path.exists(filepath):
                os.remove(filepath)
    
    return render_template('inventario/cargar_excel.html', title='Cargar Inventario desde Excel', current_rate=get_current_exchange_rate() or 0.0)

@routes_blueprint.route('/inventario/cargar_excel_confirmar', methods=['GET', 'POST'])
@login_required
def cargar_excel_confirmar():
    """
    Página de confirmación para actualizar el stock y costo de productos existentes.
    """
    if current_user.role != 'administrador':
        flash('Acceso denegado. Solo los administradores pueden realizar esta acción.', 'danger')
        return redirect(url_for('main.inventory_list'))
        
    pending_updates = session.get('pending_updates', [])
    current_rate = get_current_exchange_rate() or 0.0

    if request.method == 'POST':
        # El usuario ha confirmado, procesar las actualizaciones
        try:
            for update in pending_updates:
                product = Product.query.get(update['id'])
                if product:
                    product.stock = update['new_stock']
                    product.cost_usd = update['new_cost_usd']
                    product.name = update['new_name']
                    product.price_usd = update['new_price_usd']
                    product.image_url = update['new_image_url']
                    db.session.add(product)
            
            db.session.commit()
            flash(f'Se han actualizado {len(pending_updates)} productos exitosamente.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Ocurrió un error al confirmar la actualización: {str(e)}', 'danger')
        finally:
            session.pop('pending_updates', None) # Limpiar los datos de la sesión
        
        return redirect(url_for('main.inventory_list'))

    return render_template('inventario/cargar_excel_confirmar.html', 
                           title='Confirmar Actualización de Inventario',
                           updates=pending_updates,
                           current_rate=current_rate)

# Rutas de configuración de empresa
@routes_blueprint.route('/configuracion/empresa', methods=['GET', 'POST'])
@login_required
def company_settings():
    """
    Permite a los administradores configurar la información de la empresa.
    """
    if current_user.role != 'administrador':
        flash('Acceso denegado. Solo los administradores pueden realizar esta acción.', 'danger')
        return redirect(url_for('main.dashboard'))

    company_info = CompanyInfo.query.first()

    if request.method == 'POST':
        name = request.form.get('name')
        rif = request.form.get('rif')
        address = request.form.get('address')
        phone_numbers = request.form.get('phone_numbers')
        logo_url = request.form.get('logo_url')
        
        try:
            if company_info:
                # Actualizar información existente
                company_info.name = name
                company_info.rif = rif
                company_info.address = address
                company_info.phone_numbers = phone_numbers
                company_info.logo_url = logo_url
                db.session.commit()
                flash('Información de la empresa actualizada exitosamente!', 'success')
            else:
                # Crear nueva información
                new_info = CompanyInfo(name=name, rif=rif, address=address, phone_numbers=phone_numbers, logo_url=logo_url)
                db.session.add(new_info)
                db.session.commit()
                flash('Información de la empresa guardada exitosamente!', 'success')
            
            return redirect(url_for('main.company_settings'))
        except IntegrityError:
            db.session.rollback()
            flash('Error: El RIF ya se encuentra registrado.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Ocurrió un error al guardar la información: {str(e)}', 'danger')

    return render_template('configuracion/empresa.html', title='Configuración de Empresa', company_info=company_info, current_rate=get_current_exchange_rate() or 0.0)

# Rutas de Estructura de Costos
@routes_blueprint.route('/costos/lista')
@login_required
def cost_list():
    """Muestra la tabla resumen de la estructura de costos de los productos."""
    if current_user.role != 'administrador':
        flash('Acceso denegado. Solo los administradores pueden ver esta sección.', 'danger')
        return redirect(url_for('main.dashboard'))

    cost_structure = CostStructure.query.first()
    if not cost_structure:
        # Si no hay configuración, redirigir para crearla primero.
        flash('Por favor, configure la estructura de costos generales primero.', 'info')
        return redirect(url_for('main.cost_structure_config'))

    products = Product.query.all()
    
    # Calcular el total de ventas estimadas para distribuir los costos fijos
    total_estimated_sales = db.session.query(func.sum(Product.estimated_monthly_sales)).scalar() or 1
    if total_estimated_sales == 0:
        total_estimated_sales = 1 # Evitar división por cero

    total_fixed_costs = (cost_structure.monthly_rent or 0) + \
                        (cost_structure.monthly_utilities or 0) + \
                        (cost_structure.monthly_fixed_taxes or 0)
    
    fixed_cost_per_unit = total_fixed_costs / total_estimated_sales

    products_with_costs = []
    for product in products:
        # Usar costos variables específicos del producto si existen, si no, los por defecto.
        var_sales_exp_pct = product.variable_selling_expense_percent if product.variable_selling_expense_percent > 0 else cost_structure.default_sales_commission_percent
        var_marketing_pct = product.variable_marketing_percent if product.variable_marketing_percent > 0 else cost_structure.default_marketing_percent

        # Costo base = Costo de compra + Flete específico + Costo Fijo por unidad
        base_cost = (product.cost_usd or 0) + \
                    (product.specific_freight_cost or 0) + \
                    fixed_cost_per_unit

        # Denominador para la fórmula del precio de venta
        # P = base_cost / (1 - %gastos_var - %utilidad)
        denominator = 1 - (var_sales_exp_pct or 0) - (var_marketing_pct or 0) - (product.profit_margin or 0)

        if denominator <= 0:
            # Si los porcentajes suman 100% o más, el precio es infinito o negativo. Marcar como error.
            selling_price = 0
            profit = 0
            sales_expense = 0
            marketing_expense = 0
            error = "La suma de porcentajes de utilidad y gastos variables supera el 100%."
        else:
            selling_price = base_cost / denominator
            profit = selling_price * (product.profit_margin or 0)
            sales_expense = selling_price * (var_sales_exp_pct or 0)
            marketing_expense = selling_price * (var_marketing_pct or 0)
            error = None

        products_with_costs.append({
            'product': product,
            'fixed_cost_per_unit': fixed_cost_per_unit,
            'sales_expense': sales_expense,
            'marketing_expense': marketing_expense,
            'profit': profit,
            'selling_price': selling_price,
            'error': error
        })

    return render_template('costos/lista.html',
                           title='Estructura de Costos',
                           products_data=products_with_costs,
                           current_rate=get_current_exchange_rate() or 0.0)


@routes_blueprint.route('/costos/configuracion', methods=['GET', 'POST'])
@login_required
def cost_structure_config():
    """Permite configurar los costos fijos y variables por defecto."""
    if current_user.role != 'administrador':
        flash('Acceso denegado. Solo los administradores pueden realizar esta acción.', 'danger')
        return redirect(url_for('main.dashboard'))

    # Siempre trabajamos con la primera (y única) fila de configuración
    cost_structure = CostStructure.query.first()
    if not cost_structure:
        cost_structure = CostStructure()
        db.session.add(cost_structure)
        db.session.commit()

    if request.method == 'POST':
        try:
            cost_structure.monthly_rent = float(request.form.get('monthly_rent', 0))
            cost_structure.monthly_utilities = float(request.form.get('monthly_utilities', 0))
            cost_structure.monthly_fixed_taxes = float(request.form.get('monthly_fixed_taxes', 0))
            # Los porcentajes se guardan como decimales (ej. 5% -> 0.05)
            cost_structure.default_sales_commission_percent = float(request.form.get('default_sales_commission_percent', 0)) / 100
            cost_structure.default_marketing_percent = float(request.form.get('default_marketing_percent', 0)) / 100
            
            db.session.commit()
            flash('Configuración de costos guardada exitosamente.', 'success')
            return redirect(url_for('main.cost_list'))
        except (ValueError, TypeError) as e:
            db.session.rollback()
            flash(f'Error al guardar la configuración. Verifique que los valores sean números. Error: {e}', 'danger')

    return render_template('costos/configuracion.html',
                           title='Configurar Costos Generales',
                           cost_structure=cost_structure,
                           current_rate=get_current_exchange_rate() or 0.0)


@routes_blueprint.route('/costos/editar/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product_cost(product_id):
    """Edita la estructura de costos y utilidad para un producto específico."""
    if current_user.role != 'administrador':
        flash('Acceso denegado. Solo los administradores pueden realizar esta acción.', 'danger')
        return redirect(url_for('main.dashboard'))

    product = Product.query.get_or_404(product_id)

    if request.method == 'POST':
        try:
            # Actualizar los campos del producto desde el formulario
            product.profit_margin = float(request.form.get('profit_margin', 0)) / 100
            product.specific_freight_cost = float(request.form.get('specific_freight_cost', 0))
            product.estimated_monthly_sales = int(request.form.get('estimated_monthly_sales', 1))
            product.variable_selling_expense_percent = float(request.form.get('variable_selling_expense_percent', 0)) / 100
            product.variable_marketing_percent = float(request.form.get('variable_marketing_percent', 0)) / 100

            # --- Recalcular y actualizar el precio de venta del producto ---
            cost_structure = CostStructure.query.first()
            if not cost_structure:
                flash('La configuración de costos generales no existe. No se puede calcular el precio.', 'danger')
                return redirect(url_for('main.cost_structure_config'))

            # Se necesita recalcular el costo fijo por unidad con los datos actualizados
            total_estimated_sales = db.session.query(func.sum(Product.estimated_monthly_sales)).scalar() or 1
            if total_estimated_sales == 0: total_estimated_sales = 1

            total_fixed_costs = (cost_structure.monthly_rent or 0) + (cost_structure.monthly_utilities or 0) + (cost_structure.monthly_fixed_taxes or 0)
            fixed_cost_per_unit = total_fixed_costs / total_estimated_sales
            base_cost = (product.cost_usd or 0) + product.specific_freight_cost + fixed_cost_per_unit
            denominator = 1 - product.variable_selling_expense_percent - product.variable_marketing_percent - product.profit_margin
            if denominator <= 0:
                raise ValueError("La suma de porcentajes de utilidad y gastos variables no puede ser 100% o más.")
            new_selling_price = base_cost / denominator
            product.price_usd = round(new_selling_price, 2) # Actualizar el precio de venta final
            db.session.commit()
            flash(f'Costos y precio del producto "{product.name}" actualizados exitosamente.', 'success')
            return redirect(url_for('main.cost_list'))
        except ValueError as e:
            db.session.rollback()
            flash(f'Error al actualizar el producto: {e}', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Ocurrió un error inesperado: {e}', 'danger')

    return render_template('costos/editar.html',
                           title=f'Editar Costos de {product.name}',
                           product=product,
                           current_rate=get_current_exchange_rate() or 0.0)

@routes_blueprint.route('/ordenes/imprimir/<int:order_id>')
@login_required
def print_delivery_note(order_id):
    """
    Genera y muestra una nota de entrega en formato de recibo para imprimir.
    """
    order = Order.query.get_or_404(order_id)
    company_info = CompanyInfo.query.first()
    
    # Calcular subtotal, IVA y total con un IVA del 16%
    iva_rate = 0.16
    subtotal = order.total_amount / (1 + iva_rate)
    iva = order.total_amount - subtotal
    
    return render_template('ordenes/imprimir_nota.html', 
                           order=order,
                           company_info=company_info,
                           subtotal=subtotal,
                           iva=iva)

# Nueva ruta de API para obtener la tasa de cambio actual
@routes_blueprint.route('/api/exchange_rate')
def api_exchange_rate():
    rate = get_current_exchange_rate()
    return jsonify(rate=rate)
