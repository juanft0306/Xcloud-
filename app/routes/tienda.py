from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime
import sqlite3
import secrets
import string
from app.db.sqlite import obtener_bd
from app.utils.tasas import obtener_tasa_por_fecha, obtener_comision
from app.utils.logs import registrar_log
from app.utils.decoradores import login_requerido, negocio_requerido, rol_requerido
from app.config import Config

tienda_bp = Blueprint('tienda', __name__)

# ------------------------------------------------------------------
# FUNCIONES AUXILIARES
# ------------------------------------------------------------------
def generar_codigo_verificacion():
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(5))

def obtener_siguiente_numero_factura_con_cursor(cursor):
    cursor.execute("SELECT valor FROM configuraciones WHERE clave='prefijo_factura'")
    prefijo = (cursor.fetchone() or [''])[0] or ''
    cursor.execute("SELECT valor FROM configuraciones WHERE clave='reinicio_anual'")
    reinicio = (cursor.fetchone() or ['0'])[0] == '1'
    ano = datetime.now().year
    if reinicio:
        cursor.execute("SELECT MAX(CAST(SUBSTR(numero, LENGTH(?) + 1) AS INTEGER)) FROM facturas WHERE numero LIKE ?", (prefijo, f'{prefijo}{ano}%'))
    else:
        cursor.execute("SELECT MAX(CAST(SUBSTR(numero, LENGTH(?) + 1) AS INTEGER)) FROM facturas WHERE numero LIKE ?", (prefijo, f'{prefijo}%'))
    max_num = cursor.fetchone()[0] or 0
    return f"{prefijo}{ano}-{max_num+1:04d}" if reinicio else f"{prefijo}{max_num+1:04d}"

# ------------------------------------------------------------------
# TIENDA (listar productos)
# ------------------------------------------------------------------
@tienda_bp.route('/tienda')
@login_requerido
@negocio_requerido
@rol_requerido(['cliente'])
def tienda():
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT tiene_clientes FROM negocios WHERE id=?", (session['negocio_id'],))
        if not (c.fetchone() or [1])[0]:
            flash('Tienda no disponible.', 'warning')
            return redirect(url_for('dashboard.dashboard_negocio'))
    bd = obtener_bd()
    cursor = bd.cursor()
    productos = cursor.execute("SELECT sku, descripcion, costo_usd, stock, imagen_url FROM productos WHERE stock > 0").fetchall()
    return render_template('tienda.html', productos=productos)

# ------------------------------------------------------------------
# AGREGAR AL CARRITO
# ------------------------------------------------------------------
@tienda_bp.route('/carrito/agregar', methods=['POST'])
@login_requerido
@negocio_requerido
@rol_requerido(['cliente'])
def agregar_carrito():
    sku = request.form['sku']
    try:
        cantidad = int(request.form['cantidad'])
        if cantidad < 1:
            raise ValueError
    except:
        flash('Cantidad inválida', 'danger')
        return redirect(url_for('tienda.tienda'))
    
    carrito = session.get('carrito', [])
    for item in carrito:
        if item['sku'] == sku:
            item['cantidad'] += cantidad
            break
    else:
        carrito.append({'sku': sku, 'cantidad': cantidad})
    session['carrito'] = carrito
    flash('Producto añadido al carrito', 'success')
    return redirect(url_for('tienda.tienda'))

# ------------------------------------------------------------------
# VER CARRITO
# ------------------------------------------------------------------
@tienda_bp.route('/carrito')
@login_requerido
@negocio_requerido
@rol_requerido(['cliente'])
def ver_carrito():
    carrito = session.get('carrito', [])
    if not carrito:
        flash('Carrito vacío', 'info')
        return redirect(url_for('tienda.tienda'))
    bd = obtener_bd()
    cursor = bd.cursor()
    items = []
    total = 0
    for item in carrito:
        prod = cursor.execute("SELECT descripcion, costo_usd FROM productos WHERE sku=?", (item['sku'],)).fetchone()
        if prod:
            subtotal = prod['costo_usd'] * item['cantidad']
            total += subtotal
            items.append({'sku': item['sku'], 'descripcion': prod['descripcion'],
                          'precio': prod['costo_usd'], 'cantidad': item['cantidad'],
                          'subtotal': subtotal})
    return render_template('carrito.html', items=items, total=total)

# ------------------------------------------------------------------
# ELIMINAR DEL CARRITO
# ------------------------------------------------------------------
@tienda_bp.route('/carrito/eliminar/<sku>')
@login_requerido
@rol_requerido(['cliente'])
def eliminar_carrito(sku):
    carrito = session.get('carrito', [])
    session['carrito'] = [item for item in carrito if item['sku'] != sku]
    flash('Producto eliminado del carrito', 'info')
    return redirect(url_for('tienda.ver_carrito'))

# ------------------------------------------------------------------
# REALIZAR PEDIDO
# ------------------------------------------------------------------
@tienda_bp.route('/pedido/realizar', methods=['POST'])
@login_requerido
@negocio_requerido
@rol_requerido(['cliente'])
def realizar_pedido():
    carrito = session.get('carrito', [])
    if not carrito:
        flash('Carrito vacío', 'danger')
        return redirect(url_for('tienda.tienda'))
    
    metodo_pago = request.form.get('metodo_pago', 'Efectivo')
    bd_negocio = obtener_bd()
    cursor_negocio = bd_negocio.cursor()
    total = 0.0
    detalle = []
    
    # Verificar stock y calcular total
    for item in carrito:
        prod = cursor_negocio.execute("SELECT costo_usd, stock FROM productos WHERE sku=?", (item['sku'],)).fetchone()
        if not prod or prod['stock'] < item['cantidad']:
            flash(f'Stock insuficiente para {item["sku"]}', 'danger')
            return redirect(url_for('tienda.ver_carrito'))
        subtotal = prod['costo_usd'] * item['cantidad']
        total += subtotal
        detalle.append((item['sku'], item['cantidad'], prod['costo_usd']))

    fecha_venta = datetime.now().strftime('%Y-%m-%d')
    tasa_venta = obtener_tasa_por_fecha(fecha_venta)
    comision_pct = obtener_comision()
    monto_comision = total * (comision_pct / 100)
    total_final = total + monto_comision
    codigo_verificacion = generar_codigo_verificacion()

    # Iniciar transacción en la BD del negocio
    bd_negocio.execute("BEGIN")
    try:
        # Actualizar stock
        for sku, cant, _ in detalle:
            cursor_negocio.execute("UPDATE productos SET stock = stock - ? WHERE sku = ?", (cant, sku))

        # Crear asiento contable
        num_factura = obtener_siguiente_numero_factura_con_cursor(cursor_negocio)
        cursor_negocio.execute("INSERT INTO asientos (fecha, concepto, referencia, usuario, numero_factura, tasa_usada) VALUES (?,?,?,?,?,?)",
                               (fecha_venta, f"Pedido - {session.get('usuario_nombre','Cliente')}", "Tienda",
                                session.get('usuario_nombre','Usuario'), num_factura, tasa_venta))
        asiento_id = cursor_negocio.lastrowid
        cuenta_caja = f"Caja {metodo_pago}"

        # Movimientos contables
        cursor_negocio.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,?,0)",
                               (asiento_id, cuenta_caja, total_final))
        cursor_negocio.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,0,?)",
                               (asiento_id, "Ingresos por Ventas", total))

        if monto_comision > 0:
            cursor_negocio.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,?,0)",
                                   (asiento_id, "Comisión Sistema", monto_comision))
            cursor_negocio.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,0,?)",
                                   (asiento_id, "Ingresos por Comisión", monto_comision))

        total_costo = sum(cant * costo for _, cant, costo in detalle)
        cursor_negocio.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,?,0)",
                               (asiento_id, "Costo de Ventas", total_costo))
        cursor_negocio.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,0,?)",
                               (asiento_id, "Inventario de Mercancía", total_costo))

        # Crear factura
        cursor_negocio.execute("INSERT INTO facturas (numero, fecha, cliente, total_usd, metodo_pago, asiento_id) VALUES (?,?,?,?,?,?)",
                               (num_factura, fecha_venta, session.get('usuario_nombre','Cliente'), total_final, metodo_pago, asiento_id))

        # Detalle de venta
        for sku, cant, precio in detalle:
            cursor_negocio.execute("INSERT INTO venta_detalle (factura_numero, sku, cantidad, precio_unitario_usd) VALUES (?,?,?,?)",
                                   (num_factura, sku, cant, precio))
        bd_negocio.commit()
    except Exception as e:
        bd_negocio.rollback()
        flash(f'Error al procesar el pedido: {str(e)}', 'danger')
        return redirect(url_for('tienda.ver_carrito'))

    # Registrar pedido en la BD del sistema
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute("INSERT INTO pedidos (cliente_id, negocio_id, fecha_pedido, total_usd, metodo_pago, estado, codigo_verificacion) VALUES (?,?,?,?,?,?,?)",
                  (session['usuario_id'], session['negocio_id'], fecha, total_final, metodo_pago, 'aprobado', codigo_verificacion))
        pedido_id = c.lastrowid
        for sku, cant, precio in detalle:
            c.execute("INSERT INTO detalle_pedido (pedido_id, sku, cantidad, precio_unitario_usd) VALUES (?,?,?,?)",
                      (pedido_id, sku, cant, precio))
        conn.commit()

    session['carrito'] = []
    registrar_log("Pedido realizado", session['usuario_id'], f"Pedido #{pedido_id}")
    flash('Pedido realizado con éxito.', 'success')
    flash(f'Código de entrega: {codigo_verificacion}', 'warning')
    return redirect(url_for('tienda.mis_pedidos'))

# ------------------------------------------------------------------
# MIS PEDIDOS (historial del cliente)
# ------------------------------------------------------------------
@tienda_bp.route('/mis_pedidos')
@login_requerido
@negocio_requerido
@rol_requerido(['cliente'])
def mis_pedidos():
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT id, fecha_pedido, total_usd, estado, metodo_pago, codigo_verificacion FROM pedidos WHERE cliente_id=? AND negocio_id=? ORDER BY fecha_pedido DESC",
                  (session['usuario_id'], session['negocio_id']))
        pedidos = c.fetchall()
    return render_template('mis_pedidos.html', pedidos=pedidos)
