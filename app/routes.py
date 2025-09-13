import os
import requests
import re
from flask import Blueprint, render_template, url_for, flash, redirect, request, jsonify, session, current_app
from flask_login import login_user, current_user, logout_user, login_required
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, extract, or_
import openpyxl
from datetime import datetime, timedelta, date
from flask import Response
import time
import io
import json
import base64
# Import extensions from the new extensions file
from .extensions import db, bcrypt, socketio
from .models import User, Product, Client, Provider, Order, OrderItem, Purchase, PurchaseItem, Reception, Movement, CompanyInfo, CostStructure, Notification, ExchangeRate, get_current_time_ve, Bank, PointOfSale, CashBox, Payment, ManualFinancialMovement

# ReportLab imports for PDF generation
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode import code128
from reportlab.graphics import renderPM
from reportlab.graphics.shapes import Drawing

def get_main_calculation_currency_info():
    """Returns the main calculation currency and its symbol."""
    company_info = CompanyInfo.query.first()
    currency = company_info.calculation_currency if company_info and company_info.calculation_currency else 'USD'
    symbol = '€' if currency == 'EUR' else '$'
    return currency, symbol

routes_blueprint = Blueprint('main', __name__)

# --- INICIO DE SECCIÓN DE TASAS DE CAMBIO ---

def obtener_tasas_exchangerate_api():
    """
    Obtiene las tasas de cambio desde exchangerate-api.com.
    Retorna un diccionario con las tasas de interés.
    """
    current_app.logger.info("Obteniendo tasas desde exchangerate-api.com...")
    api_url = "https://api.exchangerate-api.com/v4/latest/USD"
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data or 'rates' not in data:
            current_app.logger.warning("La respuesta de la API de exchangerate-api no contiene datos de tasas.")
            return None

        rates = data.get('rates')
        usd_ves_rate = rates.get('VES')
        usd_eur_rate = rates.get('EUR')

        if not usd_ves_rate or not usd_eur_rate:
            current_app.logger.error("No se pudieron encontrar las tasas VES o EUR en la respuesta.")
            return None

        # 1 EUR = (1 / usd_eur_rate) USD
        # 1 USD = usd_ves_rate VES
        # 1 EUR = (1 / usd_eur_rate) * usd_ves_rate VES
        eur_ves_rate = usd_ves_rate / usd_eur_rate

        current_app.logger.info(f"API de exchangerate-api exitosa. USD/VES: {usd_ves_rate}, EUR/VES: {eur_ves_rate}")
        return {
            'USD': usd_ves_rate,
            'EUR': eur_ves_rate
        }

    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Falló la petición a la API de exchangerate-api: {e}")
        return None
    except (ValueError, TypeError, KeyError) as e:
        current_app.logger.error(f"Error procesando la respuesta de la API de exchangerate-api: {e}")
        return None

# --- NUEVAS FUNCIONES AUXILIARES ---
def get_cached_exchange_rate(currency='USD'):
    """
    Obtiene la última tasa de cambio guardada en la base de datos para una moneda específica.
    """
    try:
        cached_rate = ExchangeRate.query.filter_by(currency=currency).order_by(ExchangeRate.date_updated.desc()).first()
        if cached_rate:
            return cached_rate.rate
    except Exception as e:
        current_app.logger.error(f"Error al obtener la tasa de cambio '{currency}' de la base de datos: {e}")
        db.session.rollback()
    
    current_app.logger.warning(f"No se encontró una tasa de cambio para '{currency}' en la base de datos.")
    return None

def fetch_and_update_exchange_rate():
    """
    Obtiene las tasas de cambio actuales VES/USD y VES/EUR de exchangerate-api.com y las guarda en la BD.
    """
    rates = obtener_tasas_exchangerate_api()

    if rates:
        try:
            for currency, rate_value in rates.items():
                exchange_rate_entry = ExchangeRate.query.filter_by(currency=currency).first()
                if exchange_rate_entry:
                    exchange_rate_entry.rate = rate_value
                    exchange_rate_entry.date_updated = get_current_time_ve()
                else:
                    exchange_rate_entry = ExchangeRate(currency=currency, rate=rate_value)
                    db.session.add(exchange_rate_entry)
            
            db.session.commit()
            current_app.logger.info(f"Tasas de cambio actualizadas en la base de datos: {rates}")
            return rates
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
        db.session.rollback()
        return dict(unread_notifications=[], unread_notification_count=0)

@routes_blueprint.context_processor
def inject_pending_withdrawals_count():
    if not current_user.is_authenticated or current_user.role != 'administrador':
        return dict(pending_withdrawals_count=0)
    
    try:
        count = ManualFinancialMovement.query.filter_by(status='Pendiente', movement_type='Egreso').count()
        return dict(pending_withdrawals_count=count)
    except Exception as e:
        current_app.logger.error(f"Error al obtener el conteo de retiros pendientes: {e}")
        db.session.rollback()
        return dict(pending_withdrawals_count=0)


@routes_blueprint.route('/set-display-currency', methods=['POST'])
def set_display_currency():
    """Sets the display currency in the user's session."""
    currency = request.form.get('currency')
    if currency in ['USD', 'EUR']:
        session['display_currency'] = currency
        flash(f'Moneda de cálculo cambiada a {currency}.', 'success')
    
    referrer = request.referrer
    return redirect(referrer) if referrer else redirect(url_for('main.dashboard'))

@routes_blueprint.context_processor
def inject_current_rate():
    """
    Injects the display currency, its symbol, and its exchange rate into the context for all templates.
    The currency is determined by session preference, falling back to company settings.
    """
    # 1. Determine the currency to use for display/calculation.
    # Priority: Session > Company Setting > Default 'USD'
    company_info = CompanyInfo.query.first()
    default_currency = company_info.calculation_currency if company_info and company_info.calculation_currency else 'USD'
    
    # The session stores the user's preference for this session.
    display_currency = session.get('display_currency', default_currency)

    # 2. Get the corresponding rate and symbol.
    rate = get_cached_exchange_rate(display_currency) or 0.0
    symbol = '€' if display_currency == 'EUR' else '$'
    
    # 3. Inject into context. The templates will use these variables.
    # 'calculation_currency' will be either 'USD' or 'EUR'.
    # 'current_rate' will be the rate for that currency to VES.
    # 'currency_symbol' will be '$' or '€'.
    return dict(
        current_rate=rate, 
        calculation_currency=display_currency, 
        currency_symbol=symbol
    )

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
        if current_user.role == 'administrador':
            return redirect(url_for('main.dashboard'))
        else:
            return redirect(url_for('main.new_order'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            if user.role == 'administrador':
                return redirect(url_for('main.dashboard'))
            return redirect(url_for('main.new_order'))
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
    if current_user.role != 'administrador':
        return redirect(url_for('main.new_order'))

    total_products = Product.query.count()
    total_stock = db.session.query(db.func.sum(Product.stock)).scalar() or 0
    total_clients = Client.query.count()
    total_orders = Order.query.count()
    
    recent_products = Product.query.order_by(Product.id.desc()).limit(5).all()
    recent_orders = Order.query.order_by(Order.date_created.desc()).limit(5).all()

    return render_template('index.html', title='Dashboard',
                           total_products=total_products,
                           total_stock=total_stock,
                           total_clients=total_clients,
                           total_orders=total_orders,
                           recent_products=recent_products,
                           recent_orders=recent_orders)

# Rutas de productos (Inventario)
@routes_blueprint.route('/inventario/lista')
@login_required
def inventory_list():
    search_term = request.args.get('search', '').strip()
    group_filter = request.args.get('group', '').strip()

    query = Product.query

    if group_filter:
        query = query.filter(Product.grupo == group_filter)

    if search_term:
        search_pattern = f'%{search_term}%'
        query = query.filter(or_(
            Product.name.ilike(search_pattern),
            Product.barcode.ilike(search_pattern),
            Product.codigo_producto.ilike(search_pattern),
            Product.marca.ilike(search_pattern),
            Product.size.ilike(search_pattern)
        ))

    products = query.order_by(Product.name).all()
    
    # Obtener todos los grupos únicos para el menú desplegable de filtro
    groups = db.session.query(Product.grupo).distinct().order_by(Product.grupo).all()
    product_groups = [g[0] for g in groups if g[0]]

    user_role = current_user.role if current_user.is_authenticated else 'invitado'
    return render_template('inventario/lista.html',
                           title='Lista de Inventario',
                           products=products,
                           user_role=user_role,
                           product_groups=product_groups,
                           filters={'search': search_term, 'group': group_filter})

@routes_blueprint.route('/inventario/codigos_barra', methods=['GET'])
@login_required
def codigos_barra():
    if current_user.role != 'administrador':
        flash('Acceso denegado. Solo los administradores pueden ver esta sección.', 'danger')
        return redirect(url_for('main.new_order'))

    products = Product.query.all()
    groups = db.session.query(Product.grupo).distinct().order_by(Product.grupo).all()
    product_groups = [g[0] for g in groups if g[0]]
    return render_template('inventario/codigos_barra.html', title='Imprimir Códigos de Barra', products=products, product_groups=product_groups)

@routes_blueprint.route('/inventario/codigos_barra_api', methods=['GET']) # type: ignore
@login_required
def codigos_barra_api():
    if current_user.role != 'administrador':
        return jsonify(error='Acceso denegado'), 403

    search_term = request.args.get('search', '').lower()
    group_filter = request.args.get('group', '').strip()
    query = Product.query

    if group_filter:
        query = query.filter(Product.grupo == group_filter)

    if search_term:
        query = query.filter(or_(
            Product.name.ilike(f'%{search_term}%'),
            Product.barcode.ilike(f'%{search_term}%')
        ))
    products = query.all()
    return jsonify(products=[{'id': p.id, 'name': p.name, 'barcode': p.barcode} for p in products])

def generate_barcode_pdf_reportlab(products, company_info, currency_symbol):
    """
    Generate PDF with barcodes using ReportLab for better performance.
    Layout: 4 columns x 10 rows = 40 labels per page
    """
    # Create PDF buffer
    buffer = io.BytesIO()

    # Page dimensions
    page_width, page_height = A4
    margin = 3 * mm

    # Label dimensions (same as HTML template)
    label_width = 51 * mm
    label_height = 29 * mm

    # Create PDF canvas directly for more control
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setFont("Helvetica", 6)

    # Process products in batches of 40 (4x10 grid)
    for i in range(0, len(products), 40):
        batch = products[i:i+40]

        for j, product in enumerate(batch):
            # Calculate position in grid
            col = j % 4
            row = j // 4

            # Calculate position coordinates
            x = margin + col * label_width
            y = page_height - margin - (row + 1) * label_height

            # Company name (top right)
            if company_info and company_info.name:
                c.setFont("Helvetica-Bold", 8)
                company_name = company_info.name[:20]
                # Right align company name
                text_width = c.stringWidth(company_name, "Helvetica-Bold", 8)
                c.drawString(x + 1*mm, y + label_height - 3*mm, company_name)

            # Product name (centered, allow two lines for long names)
            c.setFont("Helvetica", 8)
            product_name = product['name'][:60]  # Allow longer names
            if len(product_name) > 30:
                # Split into two lines
                words = product_name.split()
                line1 = ""
                line2 = ""
                for word in words:
                    if len(line1 + " " + word) <= 30:
                        line1 += " " + word if line1 else word
                    else:
                        line2 += " " + word if line2 else word
                if not line2:
                    # If can't split nicely, force split
                    line1 = product_name[:30]
                    line2 = product_name[30:]
            else:
                line1 = product_name
                line2 = ""

            # Draw first line
            text_width = c.stringWidth(line1, "Helvetica", 8)
            c.drawString(x + (label_width - text_width) / 2, y + label_height - 6*mm, line1)

            # Draw second line if exists
            if line2:
                text_width = c.stringWidth(line2, "Helvetica", 8)
                c.drawString(x + (label_width - text_width) / 2, y + label_height - 9*mm, line2)

            # Price (below product name, adjust position if two lines)
            c.setFont("Helvetica-Bold", 9)
            # Cambiar el símbolo de dólar a 'ref.' para las etiquetas
            display_symbol = 'REF.' if currency_symbol == '$' else currency_symbol
            price_text = f"{display_symbol} {product['price_foreign']:.2f}"
            text_width = c.stringWidth(price_text, "Helvetica-Bold", 9)
            price_y = y + label_height - 3*mm
            c.drawString(x + label_width - text_width - 2*mm, price_y, price_text)

            # Barcode (bottom, lowered to make space)
            if product['barcode']:
                try:
                    # Calculate available width for barcode (full label width minus small margins)
                    available_width = label_width - 4*mm  # Leave 2mm margin on each side

                    # Create barcode using ReportLab with full width
                    barcode_obj = code128.Code128(
                        product['barcode'],
                        barWidth=0.45*mm,  # Slightly thinner bars to fit more
                        barHeight=12*mm,    # Taller barcode
                        quiet=1
                    )

                    # Position barcode to span full width of label, lowered
                    barcode_x = x - 4*mm  # 2mm left margin
                    barcode_y = y + 6*mm  # Lowered from 6mm to 3mm to make space

                    # Draw barcode on canvas
                    barcode_obj.drawOn(c, barcode_x, barcode_y)

                    # Add barcode text below the barcode
                    c.setFont("Helvetica", 12)  # Small font for barcode text
                    barcode_text = product['barcode']
                    text_width = c.stringWidth(barcode_text, "Helvetica", 12)
                    text_x = x + (label_width - text_width) / 2  # Center the text
                    text_y = barcode_y - 4*mm  # Position below barcode

                    c.drawString(text_x, text_y, barcode_text)

                except Exception as e:
                    current_app.logger.error(f"Error generating barcode for {product['barcode']}: {e}")
                    # Draw error text instead
                    c.setFont("Helvetica-Bold", 6)
                    c.drawString(x + 2*mm, y + 4*mm, "Error")

            # Draw dashed border around the label with thinner lines and dash pattern for segmentation
            c.setLineWidth(0.5)
            c.setDash(2 * mm, 2 * mm)  # 2mm dash, 2mm gap
            c.rect(x, y, label_width, label_height, stroke=1, fill=0)
            c.setDash()  # reset dash pattern to solid

        # Start new page if there are more products
        if i + 40 < len(products):
            c.showPage()
            c.setFont("Helvetica", 6)

    # Save PDF
    c.save()

    # Get PDF data
    pdf_data = buffer.getvalue()
    buffer.close()

    return pdf_data


@routes_blueprint.route('/inventario/imprimir_codigos_barra', methods=['POST'])
@login_required
def imprimir_codigos_barra():
    if current_user.role != 'administrador':
        flash('Acceso denegado. Solo los administradores pueden realizar esta acción.', 'danger')
        return redirect(url_for('main.new_order'))

    product_ids = request.form.getlist('product_ids')
    if not product_ids:
        flash('No se seleccionó ningún producto para imprimir.', 'warning')
        return redirect(url_for('main.codigos_barra'))

    products_to_print = Product.query.filter(Product.id.in_(product_ids)).all()
    company_info = CompanyInfo.query.first()
    
    _, currency_symbol = get_main_calculation_currency_info()

    # Preparar datos de productos para ReportLab, repitiendo por existencia.
    products_dict = []
    total_labels = 0
    MAX_LABELS = 10000  # Límite para prevenir sobrecarga del servidor.

    # Primero, calcular el número total de etiquetas para verificar el límite.
    for p in products_to_print:
        total_labels += p.stock if p.stock and p.stock > 0 else 0
    
    if total_labels > MAX_LABELS:
        flash(f'Ha intentado imprimir {total_labels} etiquetas, lo cual supera el límite de {MAX_LABELS}. Por favor, seleccione menos productos.', 'danger')
        return redirect(url_for('main.codigos_barra'))

    if total_labels == 0:
        flash('Los productos seleccionados no tienen existencia. No se generaron códigos de barra.', 'warning')
        return redirect(url_for('main.codigos_barra'))

    # Si estamos dentro del límite, construir la lista de etiquetas.
    for p in products_to_print:
        if p.stock and p.stock > 0:
            price_foreign = p.price_usd if p.price_usd else 0
            for _ in range(p.stock):
                products_dict.append({
                    'id': p.id,
                    'name': p.name,
                    'barcode': p.barcode,
                    'price_foreign': price_foreign
                })

    current_app.logger.info(f"Preparando datos para generación de PDF con {len(products_dict)} etiquetas para {len(products_to_print)} productos distintos.")

    # Generate PDF with ReportLab (more efficient)
    try:
        start_time = time.time()

        pdf_data = generate_barcode_pdf_reportlab(products_dict, company_info, currency_symbol)

        generation_time = time.time() - start_time
        current_app.logger.info(f"PDF generado exitosamente con ReportLab en {generation_time:.2f} segundos")

        # Return the PDF as a response
        return Response(pdf_data, mimetype='application/pdf', headers={'Content-Disposition': 'inline; filename=codigos_de_barra.pdf'})

    except Exception as e:
        current_app.logger.error(f"Error generating PDF with ReportLab: {str(e)}")
        error_message = f"Error generando PDF: {str(e)}. Intente con menos productos o contacte al administrador."

        # Fallback: try to generate a simple error PDF with ReportLab
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4

            buffer = io.BytesIO()
            c = canvas.Canvas(buffer, pagesize=A4)
            c.drawString(100, 750, "Error generando PDF")
            c.drawString(100, 720, error_message)
            c.drawString(100, 690, f"Número de productos seleccionados: {len(products_to_print)}")
            c.drawString(100, 660, "Recomendación: Seleccione máximo 100 productos por vez.")
            c.save()

            error_pdf = buffer.getvalue()
            buffer.close()
            return Response(error_pdf, mimetype='application/pdf', headers={'Content-Disposition': 'inline; filename=error.pdf'})

        except:
            # If even error PDF fails, return plain text
            return Response(error_message, mimetype='text/plain')


@routes_blueprint.route('/inventario/existencias')
@login_required
def inventory_stock():
    products = Product.query.all()
    return render_template('inventario/existencias.html', title='Existencias', products=products)

@routes_blueprint.route('/inventario/producto/<int:product_id>')
@login_required
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template('inventario/detalle_producto.html', title=product.name, product=product)

@routes_blueprint.route('/inventario/nuevo', methods=['GET', 'POST'])
@login_required
def new_product():
    if current_user.role != 'administrador':
        flash('Acceso denegado. Solo los administradores pueden realizar esta acción.', 'danger')
        return redirect(url_for('main.new_order'))

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
            grupo = request.form.get('grupo')
            cost_usd = float(request.form.get('cost_usd'))
            price_usd = float(request.form.get('price_usd'))

            new_prod = Product(
                name=name, description=description, barcode=barcode, qr_code=qr_code,
                image_url=image_url, size=size, color=color, cost_usd=cost_usd, price_usd=price_usd, stock=0,
                codigo_producto=codigo_producto, marca=marca, grupo=grupo
            )
            db.session.add(new_prod)
            db.session.commit()
            flash('Producto creado exitosamente!', 'success')
            return redirect(url_for('main.inventory_list'))
        except (ValueError, IntegrityError) as e:
            db.session.rollback()
            flash(f'Error al crear el producto: {str(e)}', 'danger')
    return render_template('inventario/nuevo.html', title='Nuevo Producto')

# Rutas de clientes
@routes_blueprint.route('/clientes/lista')
@login_required
def client_list():
    clients = Client.query.all()
    return render_template('clientes/lista.html', title='Lista de Clientes', clients=clients)

@routes_blueprint.route('/clientes/nuevo', methods=['GET', 'POST'])
@login_required
def new_client():
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            cedula_rif = request.form.get('cedula_rif')
            email = request.form.get('email')
            phone = request.form.get('phone')
            address = request.form.get('address')
            new_cli = Client(name=name, cedula_rif=cedula_rif, email=email, phone=phone, address=address)
            db.session.add(new_cli)
            db.session.commit()
            flash('Cliente creado exitosamente!', 'success')
            return redirect(url_for('main.client_list'))
        except IntegrityError:
            db.session.rollback()
            flash('Error: El email ya está registrado.', 'danger')
    return render_template('clientes/nuevo.html', title='Nuevo Cliente')

@routes_blueprint.route('/clientes/detalle/<int:client_id>', methods=['GET', 'POST'])
@login_required
def client_detail(client_id):
    client = Client.query.get_or_404(client_id)
    
    if request.method == 'POST':
        # This handles adding a payment to an order from the client detail page
        order_id = request.form.get('order_id')
        order = Order.query.get_or_404(order_id)
        
        try:
            payment_data_json = request.form.get('payments_data')
            payment_info = json.loads(payment_data_json)[0] # Assuming one payment at a time from the modal

            payment = Payment(
                order_id=order.id,
                amount_paid=payment_info['amount_paid'],
                currency_paid=payment_info['currency_paid'],
                amount_ves_equivalent=payment_info['amount_ves_equivalent'],
                method=payment_info['method'],
                reference=payment_info.get('reference'),
                bank_id=payment_info.get('bank_id'),
                pos_id=payment_info.get('pos_id'),
                cash_box_id=payment_info.get('cash_box_id')
            )
            db.session.add(payment)
            db.session.flush() # Flush to calculate new due amount

            # Update order status if it's now fully paid
            if order.due_amount <= 0.01:
                order.status = 'Pagada'
            
            db.session.commit()
            flash(f'Abono registrado exitosamente para la orden #{order.id:09d}.', 'success')
        except (ValueError, KeyError, IndexError, TypeError) as e:
            db.session.rollback()
            current_app.logger.error(f"Error registrando abono: {e}")
            flash(f'Error al registrar el abono: {e}', 'danger')
        return redirect(url_for('main.client_detail', client_id=client.id))

    orders = Order.query.filter_by(client_id=client.id).order_by(Order.date_created.desc()).all()
    total_due = sum(order.due_amount for order in orders if order.due_amount > 0)

    # For the payment modal
    banks = Bank.query.order_by(Bank.name).all()
    points_of_sale = PointOfSale.query.order_by(PointOfSale.name).all()
    cash_boxes = CashBox.query.order_by(CashBox.name).all()

    return render_template('clientes/detalle_cliente.html',
                           title=f'Detalle de Cliente: {client.name}',
                           client=client,
                           orders=orders,
                           total_due=total_due,
                           banks=banks,
                           points_of_sale=points_of_sale,
                           cash_boxes=cash_boxes)

# Rutas de proveedores
@routes_blueprint.route('/proveedores/lista')
@login_required
def provider_list():
    if current_user.role != 'administrador':
        flash('Acceso denegado. Solo los administradores pueden ver esta sección.', 'danger')
        return redirect(url_for('main.new_order'))

    providers = Provider.query.all()
    return render_template('proveedores/lista.html', title='Lista de Proveedores', providers=providers)

@routes_blueprint.route('/proveedores/nuevo', methods=['GET', 'POST'])
@login_required
def new_provider():
    if current_user.role != 'administrador':
        flash('Acceso denegado. Solo los administradores pueden realizar esta acción.', 'danger')
        return redirect(url_for('main.new_order'))

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
    return render_template('proveedores/nuevo.html', title='Nuevo Proveedor')

# Rutas de compras
@routes_blueprint.route('/compras/lista')
@login_required
def purchase_list():
    if current_user.role != 'administrador':
        flash('Acceso denegado. Solo los administradores pueden ver esta sección.', 'danger')
        return redirect(url_for('main.new_order'))

    purchases = Purchase.query.all()
    return render_template('compras/lista.html', title='Lista de Compras', purchases=purchases)

@routes_blueprint.route('/compras/detalle/<int:purchase_id>')
@login_required
def purchase_detail(purchase_id):
    if current_user.role != 'administrador':
        flash('Acceso denegado. Solo los administradores pueden ver esta sección.', 'danger')
        return redirect(url_for('main.new_order'))

    purchase = Purchase.query.get_or_404(purchase_id)
    return render_template('compras/detalle_compra.html', title=f'Compra #{purchase.id}', purchase=purchase)

@routes_blueprint.route('/compras/nuevo', methods=['GET', 'POST'])
@login_required
def new_purchase():
    if current_user.role != 'administrador':
        flash('Acceso denegado. Solo los administradores pueden realizar esta acción.', 'danger')
        return redirect(url_for('main.new_order'))

    providers = Provider.query.all()
    products = Product.query.all()
    calculation_currency, _ = get_main_calculation_currency_info()
    current_rate = get_cached_exchange_rate(calculation_currency)

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
    
    return render_template('compras/nuevo.html', title='Nueva Compra', providers=providers, products=products)

# Rutas de recepciones
@routes_blueprint.route('/recepciones/lista')
@login_required
def reception_list():
    if current_user.role != 'administrador':
        flash('Acceso denegado. Solo los administradores pueden ver esta sección.', 'danger')
        return redirect(url_for('main.new_order'))

    receptions = Reception.query.all()
    return render_template('recepciones/lista.html', title='Lista de Recepciones', receptions=receptions)

@routes_blueprint.route('/recepciones/nueva/<int:purchase_id>', methods=['GET', 'POST'])
@login_required
def new_reception(purchase_id):
    if current_user.role != 'administrador':
        flash('Acceso denegado. Solo los administradores pueden realizar esta acción.', 'danger')
        return redirect(url_for('main.new_order'))

    purchase = Purchase.query.get_or_404(purchase_id)
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

    return render_template('recepciones/nueva.html', title='Nueva Recepción', purchase=purchase)


# Rutas de órdenes
@routes_blueprint.route('/ordenes/lista')
@login_required
def order_list():
    orders = Order.query.all()
    return render_template('ordenes/lista.html', title='Lista de Órdenes', orders=orders)

@routes_blueprint.route('/ordenes/detalle/<int:order_id>')
@login_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    company_info = CompanyInfo.query.first()
    # IVA desactivado
    subtotal = sum(item.price * item.quantity for item in order.items)
    iva = 0
    return render_template('ordenes/detalle_orden.html',
                           title=f'Orden #{order.id}',
                           order=order,
                           company_info=company_info,
                           subtotal=subtotal,
                           iva=iva)

@routes_blueprint.route('/ordenes/nuevo', methods=['GET', 'POST'])
@login_required
def new_order():
    clients = Client.query.all()
    products = Product.query.all()
    calculation_currency, _ = get_main_calculation_currency_info()
    banks = Bank.query.order_by(Bank.name).all()
    points_of_sale = PointOfSale.query.order_by(PointOfSale.name).all()
    cash_boxes = CashBox.query.order_by(CashBox.name).all()

    current_rate = get_cached_exchange_rate(calculation_currency)
    
    if current_rate is None:
        flash('No se ha podido obtener la tasa de cambio. No se pueden crear órdenes en este momento.', 'danger')
        return redirect(url_for('main.order_list'))
    
    if request.method == 'POST':
        client_id = request.form.get('client_id')
        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')
        prices_usd = request.form.getlist('price_usd[]')
        payments_data_json = request.form.get('payments_data')
        is_credit_sale = request.form.get('is_credit_sale') == 'on'
        discount_usd = float(request.form.get('discount_usd', 0.0))
        payments_data = json.loads(payments_data_json) if payments_data_json else []
        
        try:
            # Validar que el total pagado cubra el total de la orden
            order_total_ves_before_discount = 0
            for q, p_usd in zip(quantities, prices_usd):
                order_total_ves_before_discount += (int(q) * float(p_usd) * current_rate)
            # IVA desactivado. La línea de cálculo de IVA se ha eliminado.

            discount_ves = discount_usd * current_rate
            final_order_total_ves = order_total_ves_before_discount - discount_ves

            paid_total_ves = sum(p['amount_ves_equivalent'] for p in payments_data)

            if not is_credit_sale:
                if paid_total_ves < final_order_total_ves - 0.01: # Permitir pequeñas diferencias de redondeo
                    raise ValueError(f"El monto pagado (Bs. {paid_total_ves:.2f}) es menor que el total de la orden con descuento (Bs. {final_order_total_ves:.2f}).")

            new_order = Order(client_id=client_id, status='Pendiente', total_amount=0, discount_usd=discount_usd)
            db.session.add(new_order)
            db.session.flush()

            total_amount = 0
            for p_id, q, p_usd in zip(product_ids, quantities, prices_usd):
                product = Product.query.get(p_id)
                quantity = int(q)
                
                if not product or quantity <= 0:
                    continue

                if product.stock < quantity:
                    current_app.logger.warning(f"Intento de venta con stock insuficiente - Producto: {product.name} (ID: {product.id}), Stock disponible: {product.stock}, Cantidad solicitada: {quantity}")
                    raise ValueError(f'Stock insuficiente para el producto "{product.name}". Stock disponible: {product.stock}, Cantidad solicitada: {quantity}. Por favor, ajuste la cantidad o contacte al administrador para reponer inventario.')

                price_ves = float(p_usd) * current_rate
                cost_ves = product.cost_usd * current_rate if product.cost_usd else 0
                
                item = OrderItem(
                    order_id=new_order.id,
                    product_id=p_id,
                    quantity=quantity,
                    price=price_ves,
                    cost_at_sale_ves=cost_ves
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

            new_order.total_amount = total_amount - discount_ves # Guardar el total con descuento
            db.session.flush() # Flush to allow due_amount property to calculate correctly

            # Set order status
            if is_credit_sale:
                if new_order.due_amount > 0.01:
                    new_order.status = 'Crédito'
                else:
                    new_order.status = 'Pagada' # Paid in full even if marked as credit
            else:
                new_order.status = 'Completada'

            # Procesar pagos
            for payment_info in payments_data:
                payment = Payment(
                    order_id=new_order.id,
                    amount_paid=payment_info['amount_paid'],
                    currency_paid=payment_info['currency_paid'],
                    amount_ves_equivalent=payment_info['amount_ves_equivalent'],
                    method=payment_info['method'],
                    reference=payment_info.get('reference'),
                    bank_id=payment_info.get('bank_id'),
                    pos_id=payment_info.get('pos_id'),
                    cash_box_id=payment_info.get('cash_box_id')
                )
                db.session.add(payment)

                # Actualizar saldos
                if payment.bank_id:
                    bank = Bank.query.get(payment.bank_id)
                    if bank: bank.balance += payment.amount_ves_equivalent
                elif payment.pos_id:
                    pos = PointOfSale.query.get(payment.pos_id)
                    if pos and pos.bank: pos.bank.balance += payment.amount_ves_equivalent
                elif payment.cash_box_id:
                    cash_box = CashBox.query.get(payment.cash_box_id)
                    if cash_box:
                        if payment.currency_paid == 'VES':
                            cash_box.balance_ves += payment.amount_paid
                        elif payment.currency_paid == 'USD':
                            cash_box.balance_usd += payment.amount_paid

            notification_message = f"Nueva Nota de Entrega #{new_order.id:09d} creada."
            notification_link = url_for('main.order_detail', order_id=new_order.id)
            create_notification_for_admins(notification_message, notification_link)

            db.session.commit()
            flash('Orden de venta creada exitosamente! Preparando para imprimir...', 'success')
            return redirect(url_for('main.print_delivery_note', order_id=new_order.id))
        except (ValueError, IntegrityError) as e:
            db.session.rollback()
            flash(f'Error al crear la orden: {str(e)}', 'danger')
            return redirect(url_for('main.new_order'))

    # Obtener la última orden creada para ofrecer la opción de reimprimir
    last_order = Order.query.order_by(Order.id.desc()).first()

    return render_template('ordenes/nuevo.html', 
                           title='Nueva Orden de Venta', 
                           clients=clients, 
                           products=products, 
                           banks=banks, 
                           points_of_sale=points_of_sale, 
                           cash_boxes=cash_boxes,
                           last_order=last_order)


# Nueva ruta para movimientos de inventario
@routes_blueprint.route('/movimientos/lista')
@login_required
def movement_list():
    product_id = request.args.get('product_id', default=None, type=int)
    start_date_str = request.args.get('start_date', default=None)
    end_date_str = request.args.get('end_date', default=None)

    query = Movement.query

    if product_id:
        query = query.filter(Movement.product_id == product_id)

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            query = query.filter(Movement.date >= start_date)
        except ValueError:
            flash('Formato de fecha de inicio inválido. Use AAAA-MM-DD.', 'warning')
            start_date_str = None

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            query = query.filter(Movement.date < end_date + timedelta(days=1))
        except ValueError:
            flash('Formato de fecha de fin inválido. Use AAAA-MM-DD.', 'warning')
            end_date_str = None

    movements = query.order_by(Movement.date.desc()).all()
    products = Product.query.order_by(Product.name).all()
    
    return render_template('movimientos/lista.html', 
                           title='Registro de Movimientos', 
                           movements=movements, 
                           products=products,
                           filters={'product_id': product_id, 'start_date': start_date_str, 'end_date': end_date_str})

# Nueva ruta para estadísticas (modo gerencial)
@routes_blueprint.route('/estadisticas')
@login_required
def estadisticas():
    if current_user.role != 'administrador':
        flash('Acceso denegado. Solo los administradores pueden ver esta sección.', 'danger')
        return redirect(url_for('main.new_order'))

    # --- Date Filtering ---
    today = get_current_time_ve().date()
    period = request.args.get('period', 'monthly') # 'monthly', 'daily', 'custom'
    
    if period == 'daily':
        start_date_str = request.args.get('date', today.strftime('%Y-%m-%d'))
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = start_date
        except (ValueError, TypeError):
            start_date = today
            end_date = today
        view_title = f"Estadísticas para {start_date.strftime('%d/%m/%Y')}"

    elif period == 'custom':
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else date(today.year, 1, 1)
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else today
        except (ValueError, TypeError):
            start_date = date(today.year, 1, 1)
            end_date = today
        view_title = f"Estadísticas de {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}"

    else: # Default to 'monthly' for the current year
        start_date = datetime(today.year, 1, 1).date()
        end_date = today
        view_title = f"Estadísticas Mensuales para el Año {today.year}"

    # --- Data Queries ---
    order_items_query = db.session.query(OrderItem).join(Order).filter(
        Order.date_created >= datetime.combine(start_date, datetime.min.time()),
        Order.date_created <= datetime.combine(end_date, datetime.max.time())
    )

    cost_structure = CostStructure.query.first()
    if not cost_structure:
        flash('Por favor, configure la estructura de costos para ver estadísticas precisas.', 'warning')
        cost_structure = CostStructure()

    # --- Calculations ---
    stats_data = {}

    def get_period_key(dt):
        if period == 'daily' or (period == 'custom' and (end_date - start_date).days < 32):
            return dt.strftime('%Y-%m-%d')
        return dt.strftime('%Y-%m')

    for item in order_items_query.all():
        period_key = get_period_key(item.order.date_created)
        
        if period_key not in stats_data:
            stats_data[period_key] = {'sales': 0, 'cogs': 0, 'variable_expenses': 0}

        item_revenue = item.quantity * item.price
        
        item_cogs = 0
        if item.cost_at_sale_ves is not None:
            item_cogs = item.quantity * item.cost_at_sale_ves
        elif item.product and item.product.price_usd and item.product.price_usd > 0:
            approx_rate = item.price / item.product.price_usd
            item_cogs = item.quantity * (item.product.cost_usd or 0) * approx_rate
        
        var_sales_exp_pct = item.product.variable_selling_expense_percent if item.product and item.product.variable_selling_expense_percent > 0 else (cost_structure.default_sales_commission_percent or 0)
        var_marketing_pct = item.product.variable_marketing_percent if item.product and item.product.variable_marketing_percent > 0 else (cost_structure.default_marketing_percent or 0)
        item_variable_expense = item_revenue * (var_sales_exp_pct + var_marketing_pct)

        stats_data[period_key]['sales'] += item_revenue
        stats_data[period_key]['cogs'] += item_cogs
        stats_data[period_key]['variable_expenses'] += item_variable_expense

    current_rate_usd = get_cached_exchange_rate('USD') or 0
    monthly_fixed_costs_usd = (cost_structure.monthly_rent or 0) + (cost_structure.monthly_utilities or 0) + (cost_structure.monthly_fixed_taxes or 0)
    monthly_fixed_costs_ves = monthly_fixed_costs_usd * current_rate_usd
    daily_fixed_costs_ves = monthly_fixed_costs_ves / 30.44

    total_summary = {'sales': 0, 'cogs': 0, 'variable_expenses': 0, 'fixed_expenses': 0, 'gross_profit': 0, 'net_profit': 0}
    sorted_keys = sorted(stats_data.keys())

    for key in sorted_keys:
        data = stats_data[key]
        data['gross_profit'] = data['sales'] - data['cogs']
        
        is_daily_view = period == 'daily' or (period == 'custom' and (end_date - start_date).days < 32)
        data['fixed_expenses'] = daily_fixed_costs_ves if is_daily_view else monthly_fixed_costs_ves
        
        data['net_profit'] = data['gross_profit'] - data['variable_expenses'] - data['fixed_expenses']

        for k in total_summary:
            if k in data: total_summary[k] += data[k]

    # --- Chart Data Preparation ---
    chart_labels = []
    chart_sales, chart_cogs, chart_net_profit = [], [], []
    month_names_short = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

    for key in sorted_keys:
        # Check if the key is in 'YYYY-MM' format or 'YYYY-MM-DD' format
        if len(key.split('-')) == 2: # It's a monthly key
            chart_labels.append(month_names_short[int(key.split('-')[1]) - 1])
        else: # It's a daily key
            chart_labels.append(datetime.strptime(key, '%Y-%m-%d').strftime('%d/%m'))
        
        chart_sales.append(stats_data[key]['sales'])
        chart_cogs.append(stats_data[key]['cogs'])
        chart_net_profit.append(stats_data[key]['net_profit'])

    profit_loss_chart_data = {'labels': chart_labels, 'sales': chart_sales, 'cogs': chart_cogs, 'net_profit': chart_net_profit}

    # --- Other Stats (Top Products, Clients) ---
    top_products = db.session.query(
        Product.name,
        func.sum(OrderItem.quantity).label('total_sold')
    ).join(OrderItem, OrderItem.product_id == Product.id).join(Order, Order.id == OrderItem.order_id).filter(
        Order.date_created >= datetime.combine(start_date, datetime.min.time()),
        Order.date_created <= datetime.combine(end_date, datetime.max.time())
    ).group_by(Product.id).order_by(func.sum(OrderItem.quantity).desc()).limit(5).all()

    frequent_clients = db.session.query(
        Client.name,
        func.count(Order.id).label('total_orders')
    ).join(Order, Client.id == Order.client_id).filter(
        Order.date_created >= datetime.combine(start_date, datetime.min.time()),
        Order.date_created <= datetime.combine(end_date, datetime.max.time())
    ).group_by(Client.id).order_by(func.count(Order.id).desc()).limit(5).all()

    top_products_data = {'labels': [p[0] for p in top_products], 'values': [float(p[1] or 0) for p in top_products]}
    frequent_clients_data = {'labels': [c[0] for c in frequent_clients], 'values': [c[1] for c in frequent_clients]}
    
    return render_template('estadisticas.html',
                           title=view_title,
                           stats_data=stats_data,
                           total_summary=total_summary,
                           profit_loss_chart_data=profit_loss_chart_data,
                           top_products_data=top_products_data,
                           frequent_clients_data=frequent_clients_data,
                           filters={'period': period, 'start_date': start_date.strftime('%Y-%m-%d'), 'end_date': end_date.strftime('%Y-%m-%d')})

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

        # Use a temporary directory within the instance path for cross-platform compatibility
        upload_dir = os.path.join(current_app.instance_path, 'uploads')
        os.makedirs(upload_dir, exist_ok=True)
        
        filepath = os.path.join(upload_dir, file.filename)
        file.save(filepath)

        try:
            workbook = openpyxl.load_workbook(filepath, data_only=True)
            sheet = workbook.active
            
            new_products = []
            updates = []
            
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if not row[0]:
                    continue
                
                barcode = str(row[0]).strip()
                codigo_producto = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ''
                name = str(row[2]).strip()
                cost_usd = row[3] if row[3] is not None else 0
                price_usd = row[4] if row[4] is not None else 0
                stock = row[5] if row[5] is not None else 0
                image_url = row[6] if row[6] is not None else ''
                marca = str(row[7]).strip() if len(row) > 7 and row[7] is not None else ''
                color = str(row[8]).strip() if len(row) > 8 and row[8] is not None else ''
                talla = str(row[9]).strip() if len(row) > 9 and row[9] is not None else ''
                grupo = str(row[10]).strip() if len(row) > 10 and row[10] is not None else ''

                product = Product.query.filter_by(barcode=barcode).first()

                if product:
                    updates.append({
                        'id': product.id,
                        'new_codigo_producto': codigo_producto,
                        'old_codigo_producto': product.codigo_producto,
                        'name': product.name,
                        'new_name': name,
                        'new_cost_usd': float(cost_usd),
                        'old_cost_usd': product.cost_usd,
                        'new_price_usd': float(price_usd),
                        'new_stock': int(stock),
                        'old_stock': product.stock,
                        'new_image_url': image_url,
                        'new_marca': marca,
                        'old_marca': product.marca,
                        'new_color': color,
                        'old_color': product.color,
                        'new_talla': talla,
                        'old_talla': product.size,
                        'new_grupo': grupo,
                        'old_grupo': product.grupo
                    })
                else:
                    new_products.append(Product(
                        barcode=barcode,
                        codigo_producto=codigo_producto,
                        name=name,
                        cost_usd=float(cost_usd),
                        price_usd=float(price_usd),
                        stock=int(stock),
                        image_url=image_url,
                        marca=marca,
                        color=color,
                        size=talla,
                        grupo=grupo,
                        estimated_monthly_sales=100
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
    
    return render_template('inventario/cargar_excel.html', title='Cargar Inventario desde Excel')

@routes_blueprint.route('/inventario/cargar_excel_confirmar', methods=['GET', 'POST'])
@login_required
def cargar_excel_confirmar():
    if current_user.role != 'administrador':
        flash('Acceso denegado. Solo los administradores pueden realizar esta acción.', 'danger')
        return redirect(url_for('main.inventory_list'))
        
    pending_updates = session.get('pending_updates', [])
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
                        'size': update['new_talla'],
                        'grupo': update['new_grupo']
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
                           updates=pending_updates)

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
        logo_file = request.files.get('logo_file')
        calculation_currency = request.form.get('calculation_currency')
        
        # Validar que el RIF no esté duplicado, excepto para el registro actual
        existing_company_with_rif = CompanyInfo.query.filter(CompanyInfo.rif == rif).first()
        if existing_company_with_rif and (not company_info or existing_company_with_rif.id != company_info.id):
            flash('Error: El RIF ya se encuentra registrado.', 'danger')
            return redirect(url_for('main.company_settings'))

        try:
            if company_info:
                company_info.name = name
                company_info.rif = rif
                company_info.address = address
                company_info.phone_numbers = phone_numbers
                company_info.calculation_currency = calculation_currency
                
                # Handle logo file upload
                if logo_file and logo_file.filename:
                    # Create uploads directory if it doesn't exist
                    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'logos')
                    os.makedirs(upload_dir, exist_ok=True)
                    
                    # Generate unique filename
                    filename = f"logo_{company_info.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{os.path.splitext(logo_file.filename)[1]}"
                    filepath = os.path.join(upload_dir, filename)
                    
                    # Save the file
                    logo_file.save(filepath)
                    
                    # Update logo filename in database
                    company_info.logo_filename = f"uploads/logos/{filename}"
                
                db.session.commit()
                flash('Información de la empresa actualizada exitosamente!', 'success')
            else:
                new_info = CompanyInfo(
                    name=name, 
                    rif=rif, 
                    address=address, 
                    phone_numbers=phone_numbers,
                    calculation_currency=calculation_currency
                )
                db.session.add(new_info)
                db.session.flush()  # Get the ID for the new company info
                
                # Handle logo file upload for new company
                if logo_file and logo_file.filename:
                    # Create uploads directory if it doesn't exist
                    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'logos')
                    os.makedirs(upload_dir, exist_ok=True)
                    
                    # Generate unique filename
                    filename = f"logo_{new_info.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{os.path.splitext(logo_file.filename)[1]}"
                    filepath = os.path.join(upload_dir, filename)
                    
                    # Save the file
                    logo_file.save(filepath)
                    
                    # Update logo filename in database
                    new_info.logo_filename = f"uploads/logos/{filename}"
                
                db.session.commit()
                flash('Información de la empresa guardada exitosamente!', 'success')
            
            return redirect(url_for('main.company_settings'))
        except IntegrityError:
            db.session.rollback()
            flash('Error: El RIF ya se encuentra registrado.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Ocurrió un error al guardar la información: {str(e)}', 'danger')

    return render_template('configuracion/empresa.html', title='Configuración de Empresa', company_info=company_info)

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
                           products_data=products_with_costs)


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

    usd_rate = get_cached_exchange_rate('USD')
    eur_rate = get_cached_exchange_rate('EUR')
    manual_rate_required = usd_rate is None or eur_rate is None
    if manual_rate_required:
        flash('No se pudo obtener la tasa de cambio de las APIs. Por favor, ingrese un valor manualmente.', 'warning')

    return render_template('costos/configuracion.html',
                           title='Configurar Costos Generales',
                           cost_structure=cost_structure,
                           usd_rate=usd_rate or 0.0,
                           eur_rate=eur_rate or 0.0,
                           manual_rate_required=manual_rate_required,
                           exchange_rate_info_usd=ExchangeRate.query.filter_by(currency='USD').first(),
                           exchange_rate_info_eur=ExchangeRate.query.filter_by(currency='EUR').first())


@routes_blueprint.route('/costos/update_rate', methods=['POST'])
@login_required
def update_exchange_rate():
    if current_user.role != 'administrador':
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.dashboard'))

    try:
        currency = request.form.get('currency')
        manual_rate = float(request.form.get('manual_rate'))
        if manual_rate > 0 and currency in ['USD', 'EUR']:
            exchange_rate_entry = ExchangeRate.query.filter_by(currency=currency).first()
            if exchange_rate_entry:
                exchange_rate_entry.rate = manual_rate
                exchange_rate_entry.date_updated = get_current_time_ve()
            else:
                exchange_rate_entry = ExchangeRate(currency=currency, rate=manual_rate)
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
    cost_structure = CostStructure.query.first()
    
    # Calcular punto de equilibrio financiero
    break_even_data = None
    if cost_structure:
        # Calcular costos fijos totales
        total_fixed_costs = (cost_structure.monthly_rent or 0) + \
                           (cost_structure.monthly_utilities or 0) + \
                           (cost_structure.monthly_fixed_taxes or 0)
        
        # Calcular ventas mensuales estimadas totales
        total_estimated_sales = db.session.query(func.sum(Product.estimated_monthly_sales)).scalar() or 1
        if total_estimated_sales == 0:
            total_estimated_sales = 1
        
        # Calcular costos fijos por unidad
        fixed_cost_per_unit = total_fixed_costs / total_estimated_sales
        
        # Usar gastos variables específicos o los valores por defecto (asegurando que no sean None)
        var_sales_exp_pct = product.variable_selling_expense_percent if product.variable_selling_expense_percent > 0 else (cost_structure.default_sales_commission_percent or 0)
        var_marketing_pct = product.variable_marketing_percent if product.variable_marketing_percent > 0 else (cost_structure.default_marketing_percent or 0)
        
        # El precio de venta se toma directamente del producto
        selling_price = product.price_usd or 0
        base_cost = (product.cost_usd or 0) + (product.specific_freight_cost or 0) + fixed_cost_per_unit

        # Recalcular el margen de utilidad para mostrar el valor actual real
        if selling_price > 0:
            profit_margin_calc = 1 - var_sales_exp_pct - var_marketing_pct - (base_cost / selling_price)
            product.profit_margin = profit_margin_calc

            # Calcular costo variable unitario
            variable_cost_per_unit = (product.cost_usd or 0) + (product.specific_freight_cost or 0) + \
                                   (selling_price * var_sales_exp_pct) + \
                                   (selling_price * var_marketing_pct)

            # Calcular punto de equilibrio
            if selling_price > variable_cost_per_unit:
                break_even_units = total_fixed_costs / (selling_price - variable_cost_per_unit)
                break_even_amount = break_even_units * selling_price

                break_even_data = {
                    'fixed_costs_total': total_fixed_costs,
                    'fixed_cost_per_unit': fixed_cost_per_unit,
                    'variable_cost_per_unit': variable_cost_per_unit,
                    'selling_price': selling_price,
                    'break_even_units': break_even_units,
                    'break_even_amount': break_even_amount,
                    'var_sales_exp_pct': var_sales_exp_pct * 100,
                    'var_marketing_pct': var_marketing_pct * 100
                }

    if request.method == 'POST':
        try:
            # Actualizar campos del producto desde el formulario
            product.price_usd = float(request.form.get('price_usd', 0))
            product.specific_freight_cost = float(request.form.get('specific_freight_cost', 0))
            product.estimated_monthly_sales = int(request.form.get('estimated_monthly_sales', 1))
            product.variable_selling_expense_percent = float(request.form.get('variable_selling_expense_percent', 0)) / 100
            product.variable_marketing_percent = float(request.form.get('variable_marketing_percent', 0)) / 100

            if not cost_structure:
                flash('La configuración de costos generales no existe. No se puede calcular la utilidad.', 'danger')
                return redirect(url_for('main.cost_structure_config'))

            # Recalcular componentes de costo con los nuevos datos
            total_estimated_sales = db.session.query(func.sum(Product.estimated_monthly_sales)).scalar() or 1
            if total_estimated_sales == 0: total_estimated_sales = 1

            total_fixed_costs = (cost_structure.monthly_rent or 0) + (cost_structure.monthly_utilities or 0) + (cost_structure.monthly_fixed_taxes or 0)
            fixed_cost_per_unit = total_fixed_costs / total_estimated_sales
            base_cost = (product.cost_usd or 0) + product.specific_freight_cost + fixed_cost_per_unit
            
            # Recalcular y guardar el nuevo margen de utilidad
            if product.price_usd > 0:
                new_profit_margin = 1 - product.variable_selling_expense_percent - product.variable_marketing_percent - (base_cost / product.price_usd)
                product.profit_margin = new_profit_margin
                # Alertar al usuario sobre utilidad baja o negativa
                if new_profit_margin < 0:
                    flash(f'¡Atención! Con los costos y precio de venta actuales, se está generando una pérdida. Margen de utilidad: {new_profit_margin*100:.2f}%.', 'danger')
                elif new_profit_margin < 0.05: # Umbral de advertencia del 5%
                    flash(f'Advertencia: El margen de utilidad es muy bajo: {new_profit_margin*100:.2f}%.', 'warning')
            else:
                product.profit_margin = 0
                flash('El precio de venta debe ser un número positivo.', 'danger')

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
                           break_even_data=break_even_data)

@routes_blueprint.route('/ordenes/imprimir/<int:order_id>')
@login_required
def print_delivery_note(order_id):
    order = Order.query.get_or_404(order_id)
    company_info = CompanyInfo.query.first()

    # IVA desactivado
    subtotal = sum(item.price * item.quantity for item in order.items)
    iva = 0
    order_total_with_iva = order.total_amount # This is the final amount after discount

    # Calculate total paid and change
    total_paid = sum(p.amount_ves_equivalent for p in order.payments)
    change = total_paid - order_total_with_iva if total_paid > order_total_with_iva else 0.0

    # Helper function to generate barcode
    def generate_order_barcode_base64(order_id_str):
        """Generates a Code128 barcode image and returns it as a base64 string."""
        if not order_id_str:
            return None
        try:
            barcode = code128.Code128(order_id_str, barHeight=10*mm, barWidth=0.3*mm)
            drawing = Drawing(barcode.width, barcode.height)
            drawing.add(barcode)
            buffer = io.BytesIO()
            renderPM.drawToFile(drawing, buffer, fmt='PNG')
            buffer.seek(0)
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
        except Exception as e:
            current_app.logger.error(f"Error generating barcode for order ID {order_id_str}: {e}")
            return None

    barcode_base64 = generate_order_barcode_base64(f"{order.id:09d}")

    return render_template('ordenes/imprimir_nota.html',
                           order=order,
                           company_info=company_info,
                           subtotal=subtotal,
                           iva=iva,
                           change=change,
                           barcode_base64=barcode_base64)

# Nueva ruta de API para obtener la tasa de cambio actual
@routes_blueprint.route('/api/product_by_barcode/<barcode>')
@login_required
def api_product_by_barcode(barcode):
    """API endpoint to get product information by barcode."""
    product = Product.query.filter_by(barcode=barcode).first()
    if product:
        return jsonify({
            'id': product.id,
            'name': product.name,
            'codigo_producto': product.codigo_producto,
            'price_usd': product.price_usd,
            'stock': product.stock
        })
    else:
        return jsonify({'error': 'Producto no encontrado'}), 404

@routes_blueprint.route('/api/exchange_rate')
def api_exchange_rate():
    # CORRECCIÓN: Usar la nueva función para obtener la tasa en USD
    rate = get_cached_exchange_rate('USD')
    if rate:
        return jsonify(rate=rate)
    else:
        return jsonify(error="No se pudo obtener la tasa de cambio"), 500

@routes_blueprint.route('/api/search_clients')
@login_required
def api_search_clients():
    """API endpoint to search clients by cedula/rif or name."""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify(clients=[])

    # Search by cedula_rif or name (case insensitive, partial match)
    clients = Client.query.filter(
        or_(
            Client.cedula_rif.ilike(f'%{query}%'),
            Client.name.ilike(f'%{query}%')
        )
    ).limit(10).all()

    clients_data = []
    for client in clients:
        clients_data.append({
            'id': client.id,
            'name': client.name,
            'cedula_rif': client.cedula_rif,
            'email': client.email,
            'phone': client.phone,
            'address': client.address
        })

    return jsonify(clients=clients_data)

@routes_blueprint.route('/api/clientes/nuevo', methods=['POST'])
@login_required
def api_new_client():
    """API endpoint to create a new client and return its data."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No se proporcionaron datos'}), 400

    name = data.get('name')
    cedula_rif = data.get('cedula_rif')
    email = data.get('email')

    if not name:
        return jsonify({'error': 'El nombre es requerido.'}), 400

    try:
        # Check for duplicates
        if cedula_rif and Client.query.filter_by(cedula_rif=cedula_rif).first():
            return jsonify({'error': f'La Cédula/RIF "{cedula_rif}" ya está registrada.'}), 409
        
        if email and Client.query.filter_by(email=email).first():
            return jsonify({'error': f'El email "{email}" ya está registrado.'}), 409

        new_client = Client(
            name=name,
            cedula_rif=cedula_rif,
            email=email,
            phone=data.get('phone'),
            address=data.get('address')
        )
        db.session.add(new_client)
        db.session.commit()

        client_data = { 'id': new_client.id, 'name': new_client.name, 'cedula_rif': new_client.cedula_rif, 'email': new_client.email, 'phone': new_client.phone, 'address': new_client.address }
        return jsonify(client_data), 201

    except IntegrityError as e:
        db.session.rollback()
        current_app.logger.warning(f"IntegrityError al crear cliente vía API: {e}")
        return jsonify({'error': 'Error de base de datos. Es posible que el email o Cédula/RIF ya exista.'}), 409
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creando nuevo cliente vía API: {e}")
        return jsonify({'error': 'Ocurrió un error interno en el servidor.'}), 500

# --- Rutas de Finanzas ---

@routes_blueprint.route('/finanzas/bancos/lista')
@login_required
def bank_list():
    banks = Bank.query.order_by(Bank.name).all()
    return render_template('finanzas/bancos_lista.html', title='Lista de Bancos', banks=banks)

@routes_blueprint.route('/finanzas/bancos/nuevo', methods=['GET', 'POST'])
@login_required
def new_bank():
    if current_user.role != 'administrador':
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.new_order'))

    if request.method == 'POST':
        try:
            name = request.form.get('name')
            account_number = request.form.get('account_number')
            initial_balance = float(request.form.get('initial_balance', 0))
            new_bank = Bank(name=name, account_number=account_number, balance=initial_balance)
            db.session.add(new_bank)
            db.session.commit()
            flash('Banco creado exitosamente!', 'success')
            return redirect(url_for('main.bank_list'))
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash('Error: Ya existe un banco con ese nombre o número de cuenta.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Ocurrió un error inesperado: {e}', 'danger')
    return render_template('finanzas/nuevo_banco.html', title='Nuevo Banco')

@routes_blueprint.route('/finanzas/bancos/movimientos')
@login_required
def bank_movements():
    if current_user.role != 'administrador':
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.new_order'))

    banks = Bank.query.order_by(Bank.name).all()
    return render_template('finanzas/seleccionar_cuenta.html', 
                           title='Movimientos Bancarios',
                           accounts=banks,
                           account_type='bank',
                           detail_route='main.bank_movement_detail')

@routes_blueprint.route('/finanzas/bancos/movimientos/<int:bank_id>')
@login_required
def bank_movement_detail(bank_id):
    if current_user.role != 'administrador':
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.new_order'))

    bank = Bank.query.get_or_404(bank_id)
    
    # Get payments related to this bank (direct transfers and POS terminals)
    pos_ids = [pos.id for pos in bank.pos_terminals]
    payments_query = Payment.query.filter(or_(Payment.bank_id == bank_id, Payment.pos_id.in_(pos_ids)))
    
    # Get manual movements
    manual_movements_query = ManualFinancialMovement.query.filter_by(bank_id=bank_id)
    
    # Combine and prepare for sorting
    combined_movements = []
    
    # Process payments (always income in VES)
    for p in payments_query.all():
        combined_movements.append({
            'date': p.date,
            'description': f"Pago de Orden #{p.order_id:09d}",
            'income': p.amount_ves_equivalent,
            'expense': 0,
            'currency': 'VES'
        })
        
    # Process manual movements
    for m in manual_movements_query.all():
        if m.currency != 'VES': continue
        combined_movements.append({
            'date': m.date,
            'description': m.description,
            'income': m.amount if m.movement_type == 'Ingreso' else 0,
            'expense': m.amount if m.movement_type == 'Egreso' else 0,
            'currency': m.currency
        })
        
    # Sort all movements by date (newest first)
    combined_movements.sort(key=lambda x: x['date'], reverse=True)

    return render_template('finanzas/movimientos_bancarios.html', 
                           title=f'Movimientos de {bank.name}', 
                           bank=bank,
                           movements=combined_movements)

@routes_blueprint.route('/finanzas/puntos-venta/lista')
@login_required
def pos_list():
    points_of_sale = PointOfSale.query.order_by(PointOfSale.name).all()
    return render_template('finanzas/pos_lista.html', title='Puntos de Venta', points_of_sale=points_of_sale)

@routes_blueprint.route('/finanzas/puntos-venta/nuevo', methods=['GET', 'POST'])
@login_required
def new_pos():
    if current_user.role != 'administrador':
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.new_order'))

    banks = Bank.query.order_by(Bank.name).all()
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            bank_id = request.form.get('bank_id')
            if not bank_id:
                flash('Debe seleccionar un banco asociado.', 'danger')
            else:
                new_pos = PointOfSale(name=name, bank_id=bank_id)
                db.session.add(new_pos)
                db.session.commit()
                flash('Punto de Venta creado exitosamente!', 'success')
                return redirect(url_for('main.pos_list'))
        except IntegrityError:
            db.session.rollback()
            flash('Error: Ya existe un punto de venta con ese nombre.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Ocurrió un error inesperado: {e}', 'danger')
    return render_template('finanzas/nuevo_pos.html', title='Nuevo Punto de Venta', banks=banks)

@routes_blueprint.route('/finanzas/caja/lista')
@login_required
def cashbox_list():
    cash_boxes = CashBox.query.order_by(CashBox.name).all()
    return render_template('finanzas/caja_lista.html', title='Cajas', cash_boxes=cash_boxes)

@routes_blueprint.route('/finanzas/caja/nueva', methods=['GET', 'POST'])
@login_required
def new_cashbox():
    if current_user.role != 'administrador':
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.new_order'))

    if request.method == 'POST':
        try:
            name = request.form.get('name')
            balance_ves = float(request.form.get('balance_ves', 0))
            balance_usd = float(request.form.get('balance_usd', 0))
            new_box = CashBox(name=name, balance_ves=balance_ves, balance_usd=balance_usd)
            db.session.add(new_box)
            db.session.commit()
            flash('Caja creada exitosamente!', 'success')
            return redirect(url_for('main.cashbox_list'))
        except (ValueError, IntegrityError):
            db.session.rollback()
            flash('Error: Ya existe una caja con ese nombre.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Ocurrió un error inesperado: {e}', 'danger')
    return render_template('finanzas/nueva_caja.html', title='Nueva Caja')

@routes_blueprint.route('/finanzas/caja/movimientos')
@login_required
def cashbox_movements():
    if current_user.role != 'administrador':
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.new_order'))

    cash_boxes = CashBox.query.order_by(CashBox.name).all()
    return render_template('finanzas/seleccionar_cuenta.html', 
                           title='Movimientos de Caja',
                           accounts=cash_boxes,
                           account_type='cash_box',
                           detail_route='main.cashbox_movement_detail')

@routes_blueprint.route('/finanzas/caja/movimientos/<int:cash_box_id>')
@login_required
def cashbox_movement_detail(cash_box_id):
    if current_user.role != 'administrador':
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.new_order'))

    cash_box = CashBox.query.get_or_404(cash_box_id)
    
    payments_query = Payment.query.filter_by(cash_box_id=cash_box_id)
    manual_movements_query = ManualFinancialMovement.query.filter_by(cash_box_id=cash_box_id)
    
    movements_ves = []
    for p in payments_query.filter_by(currency_paid='VES').all():
        movements_ves.append({
            'id': f'P-{p.id}', 'type': 'payment', 'obj': p,
            'date': p.date, 'description': f"Pago de Orden #{p.order.id:09d}",
            'income': p.amount_paid, 'expense': 0, 'status': 'Aprobado'
        })
    for m in manual_movements_query.filter_by(currency='VES').all():
        desc = f"{m.description} (Por: {m.created_by_user.username if m.created_by_user else 'N/A'}, Recibe: {m.received_by or 'N/A'})"
        movements_ves.append({
            'id': f'M-{m.id}', 'type': 'manual', 'obj': m,
            'date': m.date, 'description': desc,
            'income': m.amount if m.movement_type == 'Ingreso' else 0,
            'expense': m.amount if m.movement_type == 'Egreso' else 0,
            'status': m.status
        })
    
    movements_usd = []
    for p in payments_query.filter_by(currency_paid='USD').all():
        movements_usd.append({
            'id': f'P-{p.id}', 'type': 'payment', 'obj': p,
            'date': p.date, 'description': f"Pago de Orden #{p.order.id:09d}",
            'income': p.amount_paid, 'expense': 0, 'status': 'Aprobado'
        })
    for m in manual_movements_query.filter_by(currency='USD').all():
        desc = f"{m.description} (Por: {m.created_by_user.username if m.created_by_user else 'N/A'}, Recibe: {m.received_by or 'N/A'})"
        movements_usd.append({
            'id': f'M-{m.id}', 'type': 'manual', 'obj': m,
            'date': m.date, 'description': desc,
            'income': m.amount if m.movement_type == 'Ingreso' else 0,
            'expense': m.amount if m.movement_type == 'Egreso' else 0,
            'status': m.status
        })
        
    movements_ves.sort(key=lambda x: x['date'], reverse=True)
    movements_usd.sort(key=lambda x: x['date'], reverse=True)

    return render_template('finanzas/movimientos_caja.html', 
                           title=f'Movimientos de {cash_box.name}', 
                           cash_box=cash_box,
                           movements_ves=movements_ves,
                           movements_usd=movements_usd)

@routes_blueprint.route('/finanzas/movimiento/nuevo', methods=['GET', 'POST'])
@login_required
def new_financial_movement():
    if current_user.role != 'administrador':
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.new_order'))

    account_type = request.args.get('account_type')
    account_id = request.args.get('account_id', type=int)

    if not account_type or not account_id:
        flash('Tipo de cuenta o ID no especificado.', 'danger')
        return redirect(url_for('main.dashboard'))

    account = None
    if account_type == 'bank':
        account = Bank.query.get_or_404(account_id)
    elif account_type == 'cash_box':
        account = CashBox.query.get_or_404(account_id)
    else:
        flash('Tipo de cuenta inválido.', 'danger')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        try:
            description = request.form.get('description')
            amount = float(request.form.get('amount'))
            currency = request.form.get('currency')
            movement_type = request.form.get('movement_type')

            if not all([description, amount, currency, movement_type]):
                raise ValueError("Todos los campos son requeridos.")
            if amount <= 0:
                raise ValueError("El monto debe ser positivo.")

            new_mov = ManualFinancialMovement(
                description=description, amount=amount, currency=currency, movement_type=movement_type
            )

            if account_type == 'bank':
                if currency != 'VES':
                    raise ValueError("Los movimientos bancarios solo pueden ser en VES.")
                new_mov.bank_id = account_id
                if movement_type == 'Ingreso':
                    account.balance += amount
                else:
                    account.balance -= amount
            elif account_type == 'cash_box':
                new_mov.cash_box_id = account_id
                if currency == 'VES':
                    if movement_type == 'Ingreso':
                        account.balance_ves += amount
                    else:
                        account.balance_ves -= amount
                elif currency == 'USD':
                    if movement_type == 'Ingreso':
                        account.balance_usd += amount
                    else:
                        account.balance_usd -= amount
                else:
                    raise ValueError("Moneda no válida para la caja.")

            db.session.add(new_mov)
            db.session.commit()

            flash('Movimiento registrado exitosamente.', 'success')
            if account_type == 'bank':
                return redirect(url_for('main.bank_movement_detail', bank_id=account_id))
            else:
                return redirect(url_for('main.cashbox_movement_detail', cash_box_id=account_id))

        except (ValueError, TypeError) as e:
            db.session.rollback()
            flash(f'Error al registrar el movimiento: {e}', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Ocurrió un error inesperado: {e}', 'danger')

    return render_template('finanzas/nuevo_movimiento.html',
                           title='Nuevo Movimiento Manual',
                           account=account,
                           account_type=account_type)

@routes_blueprint.route('/finanzas/caja/retiro', methods=['GET', 'POST'])
@login_required
def new_cash_withdrawal():
    cash_boxes = CashBox.query.order_by(CashBox.name).all()

    if request.method == 'POST':
        try:
            cash_box_id = request.form.get('cash_box_id', type=int)
            amount = float(request.form.get('amount'))
            currency = request.form.get('currency')
            description = request.form.get('description')
            received_by = request.form.get('received_by')

            if not all([cash_box_id, amount, currency, description, received_by]):
                raise ValueError("Todos los campos son requeridos.")
            if amount <= 0:
                raise ValueError("El monto debe ser positivo.")

            cash_box = CashBox.query.get_or_404(cash_box_id)

            # Always check balance before creating request
            if currency == 'VES':
                if cash_box.balance_ves < amount:
                    raise ValueError(f"Saldo insuficiente en la caja '{cash_box.name}' para VES. Saldo actual: {cash_box.balance_ves:.2f}")
            elif currency == 'USD':
                if cash_box.balance_usd < amount:
                    raise ValueError(f"Saldo insuficiente en la caja '{cash_box.name}' para USD. Saldo actual: {cash_box.balance_usd:.2f}")
            else:
                raise ValueError("Moneda no válida para la caja.")

            is_admin = current_user.role == 'administrador'
            
            new_mov = ManualFinancialMovement(
                description=description, amount=amount, currency=currency, movement_type='Egreso',
                cash_box_id=cash_box_id, received_by=received_by, created_by_user_id=current_user.id,
                status='Aprobado' if is_admin else 'Pendiente'
            )

            if is_admin:
                # Admins approve their own withdrawals instantly
                new_mov.approved_by_user_id = current_user.id
                new_mov.date_approved = get_current_time_ve()
                # Update balance
                if currency == 'VES':
                    cash_box.balance_ves -= amount
                elif currency == 'USD':
                    cash_box.balance_usd -= amount
            
            db.session.add(new_mov)
            db.session.commit()

            if is_admin:
                flash('Retiro de efectivo registrado y aprobado exitosamente. Imprimiendo recibo...', 'success')
                return redirect(url_for('main.print_withdrawal_receipt', movement_id=new_mov.id))
            else:
                # Create notification for admins
                notification_message = f"El usuario {current_user.username} solicita aprobación para un retiro de {amount:.2f} {currency}."
                notification_link = url_for('main.pending_withdrawals')
                create_notification_for_admins(notification_message, notification_link)
                
                flash('Solicitud de retiro de efectivo enviada para aprobación.', 'info')
                return redirect(url_for('main.my_withdrawals'))

        except (ValueError, TypeError) as e:
            db.session.rollback()
            flash(f'Error al registrar el retiro: {e}', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Ocurrió un error inesperado: {e}', 'danger')

    return render_template('finanzas/retiro_caja.html', title='Retiro de Efectivo de Caja', cash_boxes=cash_boxes)

@routes_blueprint.route('/finanzas/caja/retiro/imprimir/<int:movement_id>')
@login_required
def print_withdrawal_receipt(movement_id):
    movement = ManualFinancialMovement.query.get_or_404(movement_id)
    company_info = CompanyInfo.query.first()
    if movement.movement_type != 'Egreso' or not movement.cash_box_id:
        flash('Movimiento no válido para generar recibo de retiro.', 'danger')
        return redirect(url_for('main.new_order'))
    
    # New check for approval
    if movement.status != 'Aprobado':
        flash('Este retiro aún no ha sido aprobado. No se puede imprimir el recibo.', 'warning')
        if current_user.role == 'administrador':
            return redirect(url_for('main.pending_withdrawals'))
        else:
            return redirect(url_for('main.new_order'))

    return render_template('finanzas/imprimir_recibo_retiro.html', movement=movement, company_info=company_info)

@routes_blueprint.route('/finanzas/mis-retiros')
@login_required
def my_withdrawals():
    """Muestra las solicitudes de retiro creadas por el usuario actual."""
    movements = ManualFinancialMovement.query.filter_by(
        created_by_user_id=current_user.id,
        movement_type='Egreso'
    ).order_by(ManualFinancialMovement.date.desc()).all()
    
    return render_template('finanzas/mis_retiros.html', title='Mis Solicitudes de Retiro', movements=movements)

@routes_blueprint.route('/finanzas/retiros-pendientes')
@login_required
def pending_withdrawals():
    if current_user.role != 'administrador':
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.new_order'))
    
    pending = ManualFinancialMovement.query.filter_by(status='Pendiente', movement_type='Egreso').order_by(ManualFinancialMovement.date.desc()).all()
    
    return render_template('finanzas/retiros_pendientes.html', title='Retiros Pendientes de Aprobación', movements=pending)

@routes_blueprint.route('/finanzas/retiro/procesar/<int:movement_id>/<string:action>', methods=['POST'])
@login_required
def process_withdrawal(movement_id, action):
    if current_user.role != 'administrador':
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.pending_withdrawals'))

    movement = ManualFinancialMovement.query.get_or_404(movement_id)
    if movement.status != 'Pendiente':
        flash('Este retiro ya ha sido procesado.', 'warning')
        return redirect(url_for('main.pending_withdrawals'))

    try:
        if action == 'approve':
            cash_box = movement.cash_box
            if not cash_box:
                raise ValueError("El movimiento no está asociado a ninguna caja.")

            # Final balance check
            if movement.currency == 'VES':
                if cash_box.balance_ves < movement.amount:
                    raise ValueError(f"Saldo insuficiente en la caja '{cash_box.name}' para aprobar este retiro.")
                cash_box.balance_ves -= movement.amount
            elif movement.currency == 'USD':
                if cash_box.balance_usd < movement.amount:
                    raise ValueError(f"Saldo insuficiente en la caja '{cash_box.name}' para aprobar este retiro.")
                cash_box.balance_usd -= movement.amount
            
            movement.status = 'Aprobado'
            flash_message = 'Retiro aprobado y saldo de caja actualizado.'
            flash_category = 'success'

        elif action == 'reject':
            movement.status = 'Rechazado'
            flash_message = 'Retiro rechazado.'
            flash_category = 'info'
        
        else:
            raise ValueError("Acción no válida.")

        movement.approved_by_user_id = current_user.id
        movement.date_approved = get_current_time_ve()
        db.session.commit()
        flash(flash_message, flash_category)

    except (ValueError, IntegrityError) as e:
        db.session.rollback()
        flash(f'Error al procesar el retiro: {e}', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error inesperado: {e}', 'danger')

    return redirect(url_for('main.pending_withdrawals'))
