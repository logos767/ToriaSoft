import os
import requests
import re
from bs4 import BeautifulSoup
from flask import Blueprint, render_template, url_for, flash, redirect, request, jsonify, session, current_app
from flask_login import login_user, current_user, logout_user, login_required
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, extract, or_
import openpyxl
from datetime import datetime
import barcode
from barcode.writer import SVGWriter
from io import BytesIO

# Import extensions from the new extensions file
from .extensions import db, bcrypt, socketio
from .models import User, Product, Client, Provider, Order, OrderItem, Purchase, PurchaseItem, Reception, Movement, CompanyInfo, CostStructure, Notification, ExchangeRate, get_current_time_ve

def is_valid_ean13(barcode):
    if not barcode or not barcode.isdigit() or len(barcode) != 13:
        return False
    return True

routes_blueprint = Blueprint('main', __name__)

# --- INICIO DE SECCIÓN DE TASAS DE CAMBIO ---

def obtener_tasa_p2p_binance():
    """
    Obtiene el precio P2P de USDT/VES directamente desde la API de Binance.
    Este método es más robusto que el scraping.
    """
    current_app.logger.info("Obteniendo tasa P2P desde la API de Binance...")
    api_url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
    }
    payload = {
        "proMerchantAds": False,
        "payTypes": ["Bancamiga"],
        "page": 1,
        "rows": 10,
        "countries": [],
        "tradeType": "BUY",
        "asset": "USDT",
        "fiat": "VES",
        "publisherType": None
    }
    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()

        if not data or not data.get('data'):
            current_app.logger.warning("La respuesta de la API de Binance no contiene datos.")
            return None

        prices = [float(adv['adv']['price']) for adv in data['data']]
        
        if not prices:
            current_app.logger.error("No se pudieron extraer precios de la respuesta de la API.")
            return None
        
        # Calculamos el promedio de los 10 primeros para mayor estabilidad
        average_price = sum(prices[:10]) / len(prices[:10])
        current_app.logger.info(f"API de Binance exitosa. Promedio: {average_price:.2f}")
        return average_price

    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Falló la petición a la API de Binance: {e}")
        return None
    except (ValueError, TypeError, KeyError) as e:
        current_app.logger.error(f"Error procesando la respuesta de la API de Binance: {e}")
        return None

# --- INICIO DE SECCIÓN DE TASAS DE CAMBIO ---

def obtener_tasa_p2p_binance():
    """
    Obtiene el precio P2P de USDT/VES directamente desde la API de Binance.
    Este método es más robusto que el scraping.
    """
    current_app.logger.info("Obteniendo tasa P2P desde la API de Binance...")
    api_url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
    }
    payload = {
        "proMerchantAds": False,
        "payTypes": ["Bancamiga"],
        "page": 1,
        "rows": 10,
        "countries": [],
        "tradeType": "BUY",
        "asset": "USDT",
        "fiat": "VES",
        "publisherType": None
    }
    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()

        if not data or not data.get('data'):
            current_app.logger.warning("La respuesta de la API de Binance no contiene datos.")
            return None

        prices = [float(adv['adv']['price']) for adv in data['data']]
        
        if not prices:
            current_app.logger.error("No se pudieron extraer precios de la respuesta de la API.")
            return None
        
        # Calculamos el promedio de los 10 primeros para mayor estabilidad
        average_price = sum(prices[:10]) / len(prices[:10])
        current_app.logger.info(f"API de Binance exitosa. Promedio: {average_price:.2f}")
        return average_price

    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Falló la petición a la API de Binance: {e}")
        return None
    except (ValueError, TypeError, KeyError) as e:
        current_app.logger.error(f"Error procesando la respuesta de la API de Binance: {e}")
        return None

def obtener_tasa_exchangemonitor():
    """
    Obtiene la tasa de cambio desde ExchangeMonitor como fallback.
    """
    current_app.logger.info("Obteniendo tasa desde ExchangeMonitor...")
    url = "https://exchangemonitor.net/venezuela/dolar-binance"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Encontrar el h3 que contiene el precio
        price_tag = soup.find('h3')
        if not price_tag:
            current_app.logger.error("No se encontró la etiqueta de precio en ExchangeMonitor.")
            return None
            
        # Extraer el texto y limpiar
        price_text = price_tag.get_text() # "Bs.217,71 -1,12VES (-0,52%)"
        
        # Usar regex para encontrar el primer número decimal con coma
        match = re.search(r'Bs\.s*([\d,\.]+)', price_text)
        if match:
            price_str = match.group(1).replace('.', '').replace(',', '.')
            return float(price_str)
        else:
            current_app.logger.error("No se pudo extraer el precio del texto en ExchangeMonitor.")
            return None

    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Falló la petición a ExchangeMonitor: {e}")
        return None
    except (ValueError, TypeError) as e:
        current_app.logger.error(f"Error procesando la respuesta de ExchangeMonitor: {e}")
        return None

def obtener_tasa_render():
    """
    Obtiene la tasa de cambio desde la aplicación en Render.
    """
    current_app.logger.info("Obteniendo tasa desde Render...")
    url = "https://p2p-binance-0tym.onrender.com/"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if data and 'transfer_price' in data:
            current_app.logger.info(f"Tasa de Render exitosa: {data['transfer_price']}")
            return float(data['transfer_price'])
        else:
            current_app.logger.error("No se pudo extraer el precio de la respuesta de Render.")
            return None

    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Falló la petición a Render: {e}")
        return None
    except (ValueError, TypeError, KeyError) as e:
        current_app.logger.error(f"Error procesando la respuesta de Render: {e}")
        return None

# --- NUEVAS FUNCIONES AUXILIARES ---
def get_cached_exchange_rate():
    """
    Obtiene la última tasa de cambio guardada en la base de datos.
    """
    try:
        cached_rate = ExchangeRate.query.order_by(ExchangeRate.date_updated.desc()).first()
        if cached_rate:
            return cached_rate.rate
    except Exception as e:
        current_app.logger.error(f"Error al obtener la tasa de cambio de la base de datos: {e}")
    
    current_app.logger.warning("No se encontró una tasa de cambio en la base de datos.")
    return None

def fetch_and_update_exchange_rate():
    """
    Obtiene la tasa de cambio actual VES/USD de fuentes externas y la guarda en la BD.
    Prioriza la tasa P2P de Binance y, si falla, utiliza la de ExchangeMonitor.
    """
    rate = None
    # 1. Intenta obtener la tasa de Binance primero
    rate = obtener_tasa_p2p_binance()
    
    # 2. Si Binance falla, intenta con la app de Render
    if not rate:
        current_app.logger.warning("Falló la API de Binance, intentando con la app de Render.")
        rate = obtener_tasa_render()

    # 3. Si la app de Render falla, intenta con ExchangeMonitor
    if not rate:
        current_app.logger.warning("Falló la app de Render, intentando con ExchangeMonitor.")
        rate = obtener_tasa_exchangemonitor()

    # 4. Si se obtuvo una tasa de alguna API, se guarda en la BD
    if rate:
        try:
            exchange_rate_entry = ExchangeRate.query.first()
            if exchange_rate_entry:
                exchange_rate_entry.rate = rate
                exchange_rate_entry.date_updated = get_current_time_ve()
            else:
                exchange_rate_entry = ExchangeRate(rate=rate)
                db.session.add(exchange_rate_entry)
            db.session.commit()
            current_app.logger.info(f"Tasa de cambio actualizada en la base de datos: {rate}")
            return rate
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error al guardar la tasa de cambio en la base de datos: {e}")
    
    current_app.logger.error("No se pudo obtener ninguna tasa de cambio de las APIs externas.")
    return None

# --- NUEVAS FUNCIONES AUXILIARES ---
def get_cached_exchange_rate():
    """
    Obtiene la última tasa de cambio guardada en la base de datos.
    """
    try:
        cached_rate = ExchangeRate.query.order_by(ExchangeRate.date_updated.desc()).first()
        if cached_rate:
            return cached_rate.rate
    except Exception as e:
        current_app.logger.error(f"Error al obtener la tasa de cambio de la base de datos: {e}")
    
    current_app.logger.warning("No se encontró una tasa de cambio en la base de datos.")
    return None

def fetch_and_update_exchange_rate():
    """
    Obtiene la tasa de cambio actual VES/USD de fuentes externas y la guarda en la BD.
    Prioriza la tasa P2P de Binance y, si falla, utiliza la de ExchangeMonitor.
    """
    rate = None
    # 1. Intenta obtener la tasa de Binance primero
    rate = obtener_tasa_p2p_binance()
    
    # 2. Si Binance falla, intenta con ExchangeMonitor
    if not rate:
        current_app.logger.warning("Falló la API de Binance, intentando con ExchangeMonitor.")
        rate = obtener_tasa_exchangemonitor()

    # 3. Si se obtuvo una tasa de alguna API, se guarda en la BD
    if rate:
        try:
            exchange_rate_entry = ExchangeRate.query.first()
            if exchange_rate_entry:
                exchange_rate_entry.rate = rate
                exchange_rate_entry.date_updated = get_current_time_ve()
            else:
                exchange_rate_entry = ExchangeRate(rate=rate)
                db.session.add(exchange_rate_entry)
            db.session.commit()
            current_app.logger.info(f"Tasa de cambio actualizada en la base de datos: {rate}")
            return rate
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error al guardar la tasa de cambio en la base de datos: {e}")
    
    current_app.logger.error("No se pudo obtener ninguna tasa de cambio de las APIs externas.")
    return None


# --- FIN DE SECCIÓN DE TASAS DE CAMBIO ---


# --- Funciones del Sistema de Notificaciones ---

def create_notification_for_admins(message, link):
    """
    Crea una notificación para todos los usuarios con rol 'administrador'.
    """
    current_app.logger.info(f"Attempting to create notification for admins: {message}")
    try:
        admins = User.query.filter_by(role='administrador').all()
        if not admins:
            current_app.logger.warning("No admin users found to send notification.")
            return

        admin_ids = [admin.id for admin in admins]
        current_app.logger.info(f"Found admins: {admin_ids}")

        for admin in admins:
            notification = Notification(
                user_id=admin.id,
                message=message,
                link=link
            )
            db.session.add(notification)
            db.session.flush()
            current_app.logger.info(f"Notification created in DB for admin {admin.id}: {notification.message}")

            socketio.emit('new_notification', {
                'message': notification.message,
                'link': notification.link,
                'created_at': notification.created_at.strftime('%d/%m %H:%M')
            }, room=f'user_{admin.id}')
            current_app.logger.info(f"Emitted socketio event to room user_{admin.id}")

    except Exception as e:
        current_app.logger.error(f"Error al crear notificaciones para administradores: {e}")
        db.session.rollback()

@routes_blueprint.context_processor
def inject_notifications():
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
    if current_user.is_authenticated:
        from flask_socketio import join_room
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
    
    # CORRECCIÓN: Usar la nueva función para obtener la tasa
    current_rate = get_cached_exchange_rate() or 0.0

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
    products = Product.query.all()
    user_role = current_user.role if current_user.is_authenticated else 'invitado'
    # CORRECCIÓN: Usar la nueva función
    current_rate = get_cached_exchange_rate() or 0.0
    return render_template('inventario/lista.html',
                           title='Lista de Inventario',
                           products=products,
                           user_role=user_role,
                           current_rate=current_rate)

@routes_blueprint.route('/inventario/codigos_barra', methods=['GET'])
@login_required
def codigos_barra():
    products = Product.query.all()
    current_rate = get_cached_exchange_rate() or 0.0
    return render_template('inventario/codigos_barra.html', title='Imprimir Códigos de Barra', products=products, current_rate=current_rate)

@routes_blueprint.route('/inventario/codigos_barra_api', methods=['GET'])
@login_required
def codigos_barra_api():
    search_term = request.args.get('search', '').lower()
    query = Product.query
    if search_term:
        query = query.filter(or_(
            Product.name.ilike(f'%{search_term}%'),
            Product.barcode.ilike(f'%{search_term}%')
        ))
    products = query.all()
    return jsonify(products=[{'id': p.id, 'name': p.name, 'barcode': p.barcode} for p in products])

from weasyprint import HTML
from flask import Response

@routes_blueprint.route('/inventario/imprimir_codigos_barra', methods=['POST'])
@login_required
def imprimir_codigos_barra():
    product_ids = request.form.getlist('product_ids')
    if not product_ids:
        flash('No se seleccionó ningún producto para imprimir.', 'warning')
        return redirect(url_for('main.codigos_barra'))

    products_to_print = Product.query.filter(Product.id.in_(product_ids)).all()

    products_dict = [{'id': p.id, 'name': p.name, 'barcode': p.barcode} for p in products_to_print]

    # Render the HTML template with the products
    html_string = render_template('inventario/imprimir_codigos.html', products=products_dict)

    # Create a PDF from the HTML string
    pdf = HTML(string=html_string).write_pdf()

    # Return the PDF as a response
    return Response(pdf, mimetype='application/pdf', headers={'Content-Disposition': 'inline; filename=codigos_de_barra.pdf'})


@routes_blueprint.route('/inventario/existencias')
@login_required
def inventory_stock():
    products = Product.query.all()
    # CORRECCIÓN: Usar la nueva función
    current_rate = get_cached_exchange_rate() or 0.0
    return render_template('inventario/existencias.html', title='Existencias', products=products, current_rate=current_rate)

@routes_blueprint.route('/inventario/producto/<int:product_id>')
@login_required
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    # CORRECCIÓN: Usar la nueva función
    current_rate = get_cached_exchange_rate() or 0.0
    return render_template('inventario/detalle_producto.html', title=product.name, product=product, current_rate=current_rate)

@routes_blueprint.route('/inventario/nuevo', methods=['GET', 'POST'])
@login_required
def new_product():
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            description = request.form.get('description')
            barcode = request.form.get('barcode')
            qr_code = request.form.get('qr_code')
            image_url = request.form.get('image_url')
            size = request.form.get('size')
            color = request.form.get('color')
            codigo_producto = request.form.get('codigo_producto')
            marca = request.form.get('marca')
            cost_usd = float(request.form.get('cost_usd'))
            price_usd = float(request.form.get('price_usd'))

            new_prod = Product(
                name=name, description=description, barcode=barcode, qr_code=qr_code,
                image_url=image_url, size=size, color=color, cost_usd=cost_usd, price_usd=price_usd, stock=0,
                codigo_producto=codigo_producto, marca=marca
            )
            db.session.add(new_prod)
            db.session.commit()
            flash('Producto creado exitosamente!', 'success')
            return redirect(url_for('main.inventory_list'))
        except (ValueError, IntegrityError) as e:
            db.session.rollback()
            flash(f'Error al crear el producto: {str(e)}', 'danger')
    # CORRECCIÓN: Usar la nueva función
    return render_template('inventario/nuevo.html', title='Nuevo Producto', current_rate=get_cached_exchange_rate() or 0.0)

# Rutas de clientes
@routes_blueprint.route('/clientes/lista')
@login_required
def client_list():
    clients = Client.query.all()
    # CORRECCIÓN: Usar la nueva función
    current_rate = get_cached_exchange_rate() or 0.0
    return render_template('clientes/lista.html', title='Lista de Clientes', clients=clients, current_rate=current_rate)

@routes_blueprint.route('/clientes/nuevo', methods=['GET', 'POST'])
@login_required
def new_client():
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
    # CORRECCIÓN: Usar la nueva función
    return render_template('clientes/nuevo.html', title='Nuevo Cliente', current_rate=get_cached_exchange_rate() or 0.0)

# Rutas de proveedores
@routes_blueprint.route('/proveedores/lista')
@login_required
def provider_list():
    providers = Provider.query.all()
    # CORRECCIÓN: Usar la nueva función
    current_rate = get_cached_exchange_rate() or 0.0
    return render_template('proveedores/lista.html', title='Lista de Proveedores', providers=providers, current_rate=current_rate)

@routes_blueprint.route('/proveedores/nuevo', methods=['GET', 'POST'])
@login_required
def new_provider():
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
    # CORRECCIÓN: Usar la nueva función
    return render_template('proveedores/nuevo.html', title='Nuevo Proveedor', current_rate=get_cached_exchange_rate() or 0.0)

# Rutas de compras
@routes_blueprint.route('/compras/lista')
@login_required
def purchase_list():
    purchases = Purchase.query.all()
    # CORRECCIÓN: Usar la nueva función
    current_rate = get_cached_exchange_rate() or 0.0
    return render_template('compras/lista.html', title='Lista de Compras', purchases=purchases, current_rate=current_rate)

@routes_blueprint.route('/compras/detalle/<int:purchase_id>')
@login_required
def purchase_detail(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    # CORRECCIÓN: Usar la nueva función
    current_rate = get_cached_exchange_rate() or 0.0
    return render_template('compras/detalle_compra.html', title=f'Compra #{purchase.id}', purchase=purchase, current_rate=current_rate)

@routes_blueprint.route('/compras/nuevo', methods=['GET', 'POST'])
@login_required
def new_purchase():
    providers = Provider.query.all()
    products = Product.query.all()
    # CORRECCIÓN: Usar la nueva función
    current_rate = get_cached_exchange_rate()

    if current_rate is None:
        flash('No se ha podido obtener la tasa de cambio. No se pueden crear compras en este momento.', 'danger')
        return redirect(url_for('main.purchase_list'))

    if request.method == 'POST':
        try:
            provider_id = request.form.get('provider_id')
            new_purchase = Purchase(provider_id=provider_id, total_cost=0)
            db.session.add(new_purchase)
            db.session.flush()
            
            product_ids = request.form.getlist('product_id[]')
            quantities = request.form.getlist('quantity[]')
            costs_usd = request.form.getlist('cost_usd[]')

            total_cost = 0
            for p_id, q, c_usd in zip(product_ids, quantities, costs_usd):
                product = Product.query.get(p_id)
                quantity = int(q)
                if product and quantity > 0:
                    cost_ves = float(c_usd) * current_rate
                    item = PurchaseItem(
                        purchase_id=new_purchase.id,
                        product_id=p_id,
                        quantity=quantity,
                        cost=cost_ves
                    )
                    db.session.add(item)
                    total_cost += cost_ves * quantity
            
            new_purchase.total_cost = total_cost
            
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
    receptions = Reception.query.all()
    # CORRECCIÓN: Usar la nueva función
    current_rate = get_cached_exchange_rate() or 0.0
    return render_template('recepciones/lista.html', title='Lista de Recepciones', receptions=receptions, current_rate=current_rate)

@routes_blueprint.route('/recepciones/nueva/<int:purchase_id>', methods=['GET', 'POST'])
@login_required
def new_reception(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    # CORRECCIÓN: Usar la nueva función
    current_rate = get_cached_exchange_rate() or 0.0
    if request.method == 'POST':
        try:
            new_reception = Reception(purchase_id=purchase.id, status='Completada')
            db.session.add(new_reception)

            for item in purchase.items:
                product = Product.query.get(item.product_id)
                if product:
                    product.stock += item.quantity
                    db.session.add(product)
                    
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
            
            notification_message = f"Nueva recepción para la compra #{purchase.id} procesada."
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
    orders = Order.query.all()
    # CORRECCIÓN: Usar la nueva función
    current_rate = get_cached_exchange_rate() or 0.0
    return render_template('ordenes/lista.html', title='Lista de Órdenes', orders=orders, current_rate=current_rate)

@routes_blueprint.route('/ordenes/detalle/<int:order_id>')
@login_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    company_info = CompanyInfo.query.first()
    # CORRECCIÓN: Usar la nueva función
    current_rate = get_cached_exchange_rate() or 0.0
    return render_template('ordenes/detalle_orden.html', 
                           title=f'Orden #{order.id}', 
                           order=order,
                           company_info=company_info,
                           current_rate=current_rate)

@routes_blueprint.route('/ordenes/nuevo', methods=['GET', 'POST'])
@login_required
def new_order():
    clients = Client.query.all()
    products = Product.query.all()
    # CORRECCIÓN: Usar la nueva función
    current_rate = get_cached_exchange_rate()
    
    if current_rate is None:
        flash('No se ha podido obtener la tasa de cambio. No se pueden crear órdenes en este momento.', 'danger')
        return redirect(url_for('main.order_list'))
    
    if request.method == 'POST':
        client_id = request.form.get('client_id')
        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')
        prices_usd = request.form.getlist('price_usd[]')
        
        try:
            new_order = Order(client_id=client_id, status='Pendiente', total_amount=0)
            db.session.add(new_order)
            db.session.flush()

            total_amount = 0
            for p_id, q, p_usd in zip(product_ids, quantities, prices_usd):
                product = Product.query.get(p_id)
                quantity = int(q)
                
                if not product or quantity <= 0:
                    continue

                if product.stock < quantity:
                    raise ValueError(f'Stock insuficiente para el producto: {product.name}')

                price_ves = float(p_usd) * current_rate
                
                item = OrderItem(
                    order_id=new_order.id,
                    product_id=p_id,
                    quantity=quantity,
                    price=price_ves
                )
                db.session.add(item)
                
                product.stock -= quantity
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
                
                total_amount += price_ves * quantity

            new_order.total_amount = total_amount
            new_order.status = 'Completada'

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
    movements = Movement.query.order_by(Movement.date.desc()).all()
    # CORRECCIÓN: Usar la nueva función
    current_rate = get_cached_exchange_rate() or 0.0
    return render_template('movimientos/lista.html', title='Registro de Movimientos', movements=movements, current_rate=current_rate)


# Nueva ruta para estadísticas (modo gerencial)
@routes_blueprint.route('/estadisticas')
@login_required
def estadisticas():
    top_products = db.session.query(
        Product.name,
        func.sum(func.coalesce(OrderItem.quantity, 0)).label('total_sold')
    ).outerjoin(OrderItem).group_by(Product.id).order_by(func.sum(func.coalesce(OrderItem.quantity, 0)).desc()).limit(5).all()

    least_products = db.session.query(
        Product.name,
        func.sum(OrderItem.quantity).label('total_sold')
    ).join(OrderItem).group_by(Product.id).order_by('total_sold').limit(5).all()

    frequent_clients = db.session.query(
        Client.name,
        func.count(Order.id).label('total_orders')
    ).outerjoin(Order).group_by(Client.id).order_by(func.count(Order.id).desc()).limit(5).all()

    sales_by_month = db.session.query(
        extract('month', Order.date_created).label('month'),
        func.sum(Order.total_amount).label('total_sales')
    ).filter(extract('year', Order.date_created) == extract('year', func.now())).group_by('month').order_by('month').all()

    top_products_data = {'labels': [p[0] for p in top_products], 'values': [p[1] for p in top_products]}
    least_products_data = {'labels': [p[0] for p in least_products], 'values': [p[1] for p in least_products]}
    frequent_clients_data = {'labels': [c[0] for c in frequent_clients], 'values': [c[1] for c in frequent_clients]}
    
    months_names = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    monthly_sales = {int(s[0]): s[1] for s in sales_by_month}
    sales_data_complete = {'labels': months_names, 'values': [monthly_sales.get(i + 1, 0) for i in range(12)]}
    
    # CORRECCIÓN: Usar la nueva función
    current_rate = get_cached_exchange_rate() or 0.0

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
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash('Formato de archivo no válido. Solo se aceptan archivos .xlsx.', 'danger')
            return redirect(request.url)

        filepath = os.path.join('/tmp', file.filename)
        file.save(filepath)

        try:
            workbook = openpyxl.load_workbook(filepath)
            sheet = workbook.active
            
            new_products = []
            updates = []
            
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if not row[0]:
                    continue
                
                barcode = str(row[0]).strip()
                name = str(row[1]).strip()
                cost_usd = row[2] if row[2] is not None else 0
                price_usd = row[3] if row[3] is not None else 0
                stock = row[4] if row[4] is not None else 0
                image_url = row[5] if row[5] is not None else ''
                codigo_producto = str(row[6]).strip() if len(row) > 6 and row[6] is not None else ''
                marca = str(row[7]).strip() if len(row) > 7 and row[7] is not None else ''
                color = str(row[8]).strip() if len(row) > 8 and row[8] is not None else ''
                talla = str(row[9]).strip() if len(row) > 9 and row[9] is not None else ''

                product = Product.query.filter_by(barcode=barcode).first()

                if product:
                    updates.append({
                        'id': product.id,
                        'name': product.name,
                        'new_stock': int(stock),
                        'old_stock': product.stock,
                        'new_cost_usd': float(cost_usd),
                        'old_cost_usd': product.cost_usd,
                        'new_name': name,
                        'new_price_usd': float(price_usd),
                        'new_image_url': image_url,
                        'new_codigo_producto': codigo_producto,
                        'old_codigo_producto': product.codigo_producto,
                        'new_marca': marca,
                        'old_marca': product.marca,
                        'new_color': color,
                        'old_color': product.color,
                        'new_talla': talla,
                        'old_talla': product.size
                    })
                else:
                    new_products.append(Product(
                        barcode=barcode,
                        name=name,
                        cost_usd=float(cost_usd),
                        price_usd=float(price_usd),
                        stock=int(stock),
                        image_url=image_url,
                        codigo_producto=codigo_producto,
                        marca=marca,
                        color=color,
                        size=talla
                    ))

            if new_products:
                db.session.bulk_save_objects(new_products)
                flash(f'Se han agregado {len(new_products)} productos nuevos.', 'success')

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
            if os.path.exists(filepath):
                os.remove(filepath)
    
    # CORRECCIÓN: Usar la nueva función
    return render_template('inventario/cargar_excel.html', title='Cargar Inventario desde Excel', current_rate=get_cached_exchange_rate() or 0.0)

@routes_blueprint.route('/inventario/cargar_excel_confirmar', methods=['GET', 'POST'])
@login_required
def cargar_excel_confirmar():
    if current_user.role != 'administrador':
        flash('Acceso denegado. Solo los administradores pueden realizar esta acción.', 'danger')
        return redirect(url_for('main.inventory_list'))
        
    pending_updates = session.get('pending_updates', [])
    # CORRECCIÓN: Usar la nueva función
    current_rate = get_cached_exchange_rate() or 0.0

    if request.method == 'POST':
        try:
            if pending_updates:
                update_mappings = [
                    {
                        'id': update['id'],
                        'stock': update['new_stock'],
                        'cost_usd': update['new_cost_usd'],
                        'name': update['new_name'],
                        'price_usd': update['new_price_usd'],
                        'image_url': update['new_image_url'],
                        'codigo_producto': update['new_codigo_producto'],
                        'marca': update['new_marca'],
                        'color': update['new_color'],
                        'size': update['new_talla']
                    }
                    for update in pending_updates
                ]
                db.session.bulk_update_mappings(Product, update_mappings)

            db.session.commit()
            flash(f'Se han actualizado {len(pending_updates)} productos exitosamente.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Ocurrió un error al confirmar la actualización: {str(e)}', 'danger')
        finally:
            session.pop('pending_updates', None)
        
        return redirect(url_for('main.inventory_list'))

    return render_template('inventario/cargar_excel_confirmar.html', 
                           title='Confirmar Actualización de Inventario',
                           updates=pending_updates,
                           current_rate=current_rate)

# Rutas de configuración de empresa
@routes_blueprint.route('/configuracion/empresa', methods=['GET', 'POST'])
@login_required
def company_settings():
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
                company_info.name = name
                company_info.rif = rif
                company_info.address = address
                company_info.phone_numbers = phone_numbers
                company_info.logo_url = logo_url
                db.session.commit()
                flash('Información de la empresa actualizada exitosamente!', 'success')
            else:
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

    # CORRECCIÓN: Usar la nueva función
    return render_template('configuracion/empresa.html', title='Configuración de Empresa', company_info=company_info, current_rate=get_cached_exchange_rate() or 0.0)

# Rutas de Estructura de Costos
@routes_blueprint.route('/costos/lista')
@login_required
def cost_list():
    if current_user.role != 'administrador':
        flash('Acceso denegado. Solo los administradores pueden ver esta sección.', 'danger')
        return redirect(url_for('main.dashboard'))

    cost_structure = CostStructure.query.first()
    if not cost_structure:
        flash('Por favor, configure la estructura de costos generales primero.', 'info')
        return redirect(url_for('main.cost_structure_config'))

    products = Product.query.all()
    
    total_estimated_sales = db.session.query(func.sum(Product.estimated_monthly_sales)).scalar() or 1
    if total_estimated_sales == 0:
        total_estimated_sales = 1

    total_fixed_costs = (cost_structure.monthly_rent or 0) + \
                        (cost_structure.monthly_utilities or 0) + \
                        (cost_structure.monthly_fixed_taxes or 0)
    
    fixed_cost_per_unit = total_fixed_costs / total_estimated_sales

    products_with_costs = []
    for product in products:
        var_sales_exp_pct = product.variable_selling_expense_percent if product.variable_selling_expense_percent > 0 else cost_structure.default_sales_commission_percent
        var_marketing_pct = product.variable_marketing_percent if product.variable_marketing_percent > 0 else cost_structure.default_marketing_percent

        base_cost = (product.cost_usd or 0) + \
                    (product.specific_freight_cost or 0) + \
                    fixed_cost_per_unit
        
        denominator = 1 - (var_sales_exp_pct or 0) - (var_marketing_pct or 0) - (product.profit_margin or 0)

        if denominator <= 0:
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
                           # CORRECCIÓN: Usar la nueva función
                           current_rate=get_cached_exchange_rate() or 0.0)


@routes_blueprint.route('/costos/configuracion', methods=['GET', 'POST'])
@login_required
def cost_structure_config():
    if current_user.role != 'administrador':
        flash('Acceso denegado. Solo los administradores pueden realizar esta acción.', 'danger')
        return redirect(url_for('main.dashboard'))

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
            cost_structure.default_sales_commission_percent = float(request.form.get('default_sales_commission_percent', 0)) / 100
            cost_structure.default_marketing_percent = float(request.form.get('default_marketing_percent', 0)) / 100
            
            db.session.commit()
            flash('Configuración de costos guardada exitosamente.', 'success')
            return redirect(url_for('main.cost_list'))
        except (ValueError, TypeError) as e:
            db.session.rollback()
            flash(f'Error al guardar la configuración. Verifique que los valores sean números. Error: {e}', 'danger')

    current_rate = get_cached_exchange_rate()
    manual_rate_required = current_rate is None
    if manual_rate_required:
        flash('No se pudo obtener la tasa de cambio de las APIs. Por favor, ingrese un valor manualmente.', 'warning')

    return render_template('costos/configuracion.html',
                           title='Configurar Costos Generales',
                           cost_structure=cost_structure,
                           current_rate=current_rate or 0.0,
                           manual_rate_required=manual_rate_required)


@routes_blueprint.route('/costos/update_rate', methods=['POST'])
@login_required
def update_exchange_rate():
    if current_user.role != 'administrador':
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.dashboard'))

    try:
        manual_rate = float(request.form.get('manual_rate'))
        if manual_rate > 0:
            exchange_rate_entry = ExchangeRate.query.first()
            if exchange_rate_entry:
                exchange_rate_entry.rate = manual_rate
                exchange_rate_entry.date_updated = get_current_time_ve()
            else:
                exchange_rate_entry = ExchangeRate(rate=manual_rate)
                db.session.add(exchange_rate_entry)
            db.session.commit()
            flash('Tasa de cambio actualizada manualmente.', 'success')
        else:
            flash('La tasa de cambio debe ser un número positivo.', 'danger')
    except (ValueError, TypeError):
        flash('Valor de tasa de cambio inválido.', 'danger')

    return redirect(url_for('main.cost_structure_config'))


@routes_blueprint.route('/costos/editar/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product_cost(product_id):
    if current_user.role != 'administrador':
        flash('Acceso denegado. Solo los administradores pueden realizar esta acción.', 'danger')
        return redirect(url_for('main.dashboard'))

    product = Product.query.get_or_404(product_id)

    if request.method == 'POST':
        try:
            product.profit_margin = float(request.form.get('profit_margin', 0)) / 100
            product.specific_freight_cost = float(request.form.get('specific_freight_cost', 0))
            product.estimated_monthly_sales = int(request.form.get('estimated_monthly_sales', 1))
            product.variable_selling_expense_percent = float(request.form.get('variable_selling_expense_percent', 0)) / 100
            product.variable_marketing_percent = float(request.form.get('variable_marketing_percent', 0)) / 100

            cost_structure = CostStructure.query.first()
            if not cost_structure:
                flash('La configuración de costos generales no existe. No se puede calcular el precio.', 'danger')
                return redirect(url_for('main.cost_structure_config'))

            total_estimated_sales = db.session.query(func.sum(Product.estimated_monthly_sales)).scalar() or 1
            if total_estimated_sales == 0: total_estimated_sales = 1

            total_fixed_costs = (cost_structure.monthly_rent or 0) + (cost_structure.monthly_utilities or 0) + (cost_structure.monthly_fixed_taxes or 0)
            fixed_cost_per_unit = total_fixed_costs / total_estimated_sales
            base_cost = (product.cost_usd or 0) + product.specific_freight_cost + fixed_cost_per_unit
            denominator = 1 - product.variable_selling_expense_percent - product.variable_marketing_percent - product.profit_margin
            if denominator <= 0:
                raise ValueError("La suma de porcentajes de utilidad y gastos variables no puede ser 100% o más.")
            new_selling_price = base_cost / denominator
            product.price_usd = round(new_selling_price, 2)
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
                           # CORRECCIÓN: Usar la nueva función
                           current_rate=get_cached_exchange_rate() or 0.0)

@routes_blueprint.route('/ordenes/imprimir/<int:order_id>')
@login_required
def print_delivery_note(order_id):
    order = Order.query.get_or_404(order_id)
    company_info = CompanyInfo.query.first()
    
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
    # CORRECCIÓN: Usar la nueva función
    rate = get_cached_exchange_rate()
    if rate:
        return jsonify(rate=rate)
    else:
        return jsonify(error="No se pudo obtener la tasa de cambio"), 500