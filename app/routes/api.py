from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime
import json
import re
from app.db.sqlite import obtener_bd
from app.utils.tasas import obtener_tasa, obtener_tasa_por_fecha, obtener_comision
from app.utils.helpers import generar_sku_sugerido, normalizar, extraer_entidades, detectar_intencion
from app.utils.logs import registrar_log
from app.utils.decoradores import login_requerido, negocio_requerido, rol_requerido
from app.routes.ventas import obtener_siguiente_numero_factura_con_cursor
from app.config import Config

api_bp = Blueprint('api', __name__)

# ------------------------------------------------------------------
# CHATBOT - API
# ------------------------------------------------------------------
def ejecutar_intencion(intencion, entidades, texto_original):
    if intencion == 'venta':
        sku = entidades.get('sku')
        cantidad = entidades.get('cantidad', 1)
        cliente = entidades.get('cliente', 'Consumidor Final')
        metodo = entidades.get('metodo', 'Efectivo USD')
        if not sku:
            return "Necesito el SKU del producto (ej. A001)."
        bd = obtener_bd()
        cursor = bd.cursor()
        prod = cursor.execute("SELECT descripcion, costo_usd, stock FROM productos WHERE sku=?", (sku,)).fetchone()
        if not prod:
            return f"No encontré el producto {sku}."
        if prod['stock'] < cantidad:
            return f"Stock insuficiente. Solo hay {prod['stock']} unidades de {prod['descripcion']}."
        precio = entidades.get('precio', prod['costo_usd'])
        total = cantidad * precio
        comision_pct = obtener_comision()
        monto_comision = total * (comision_pct / 100)
        total_final = total + monto_comision

        metodos_validos = {'Efectivo USD': 'Efectivo', 'Pago Móvil': 'Pago Móvil', 'Transferencia': 'Transferencia'}
        metodo_normalizado = metodos_validos.get(metodo, 'Efectivo')

        bd.execute("BEGIN")
        try:
            fecha_venta = datetime.now().strftime('%Y-%m-%d')
            tasa_venta = obtener_tasa_por_fecha(fecha_venta)
            num_factura = obtener_siguiente_numero_factura_con_cursor(cursor)
            cursor.execute("INSERT INTO asientos (fecha, concepto, referencia, usuario, numero_factura, tasa_usada) VALUES (?,?,?,?,?,?)",
                           (fecha_venta, f"Venta - {cliente}", "Chatbot", session.get('usuario_nombre','Usuario'), num_factura, tasa_venta))
            asiento_id = cursor.lastrowid
            cuenta = f"Caja {metodo_normalizado}"

            cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,?,0)", (asiento_id, cuenta, total_final))
            cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,0,?)", (asiento_id, "Ingresos por Ventas", total))

            if monto_comision > 0:
                cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,?,0)", (asiento_id, "Comisión Sistema", monto_comision))
                cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,0,?)", (asiento_id, "Ingresos por Comisión", monto_comision))

            cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,?,0)", (asiento_id, "Costo de Ventas", prod['costo_usd'] * cantidad))
            cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,0,?)", (asiento_id, "Inventario de Mercancía", prod['costo_usd'] * cantidad))
            cursor.execute("INSERT INTO facturas (numero, fecha, cliente, total_usd, metodo_pago, asiento_id) VALUES (?,?,?,?,?,?)",
                           (num_factura, fecha_venta, cliente, total_final, metodo_normalizado, asiento_id))
            cursor.execute("INSERT INTO venta_detalle (factura_numero, sku, cantidad, precio_unitario_usd) VALUES (?,?,?,?)",
                           (num_factura, sku, cantidad, precio))
            cursor.execute("UPDATE productos SET stock = stock - ? WHERE sku = ?", (cantidad, sku))
            bd.commit()
            registrar_log("Venta por Luz", session['usuario_id'], f"Factura {num_factura}")
            return f"Listo. Venta registrada: Factura {num_factura}. {cantidad} x {prod['descripcion']} a ${precio:.2f} c/u. Total: ${total_final:.2f}."
        except Exception as e:
            bd.rollback()
            return f"Error: {str(e)}"

    elif intencion == 'consulta_stock':
        sku = entidades.get('sku')
        if not sku:
            return "Dime el SKU del producto (ej. A001)."
        bd = obtener_bd()
        cursor = bd.cursor()
        prod = cursor.execute("SELECT descripcion, costo_usd, stock FROM productos WHERE sku=?", (sku,)).fetchone()
        return f"{prod['descripcion']} (SKU {sku}): {prod['stock']} unidades, costo ${prod['costo_usd']:.2f}." if prod else f"No encontré {sku}."

    elif intencion == 'agregar_producto':
        nombre = entidades.get('nombre_producto')
        precio = entidades.get('precio')
        stock = entidades.get('cantidad')
        if not nombre or not precio or not stock:
            return "Dime: agrega [nombre] costo [precio] stock [cantidad]"
        bd = obtener_bd()
        cursor = bd.cursor()
        sku = generar_sku_sugerido()
        cursor.execute("INSERT INTO productos (sku, descripcion, costo_usd, stock) VALUES (?,?,?,?)", (sku, nombre, precio, stock))
        bd.commit()
        return f"'{nombre}' agregado con SKU {sku}."

    elif intencion == 'caja':
        bd = obtener_bd()
        cursor = bd.cursor()
        ingresos = cursor.execute("SELECT SUM(debe) - SUM(haber) FROM movimientos WHERE cuenta LIKE 'Caja %'").fetchone()[0] or 0
        return f"Saldo actual en caja: ${ingresos:.2f}."

    elif intencion == 'gasto':
        concepto = entidades.get('concepto', 'Gasto general')
        monto = entidades.get('precio') or entidades.get('cantidad')
        if not monto:
            return "Dime el monto del gasto."
        bd = obtener_bd()
        cursor = bd.cursor()
        fecha = datetime.now().strftime('%Y-%m-%d')
        bd.execute("BEGIN")
        try:
            cursor.execute("INSERT INTO asientos (fecha, concepto, usuario) VALUES (?,?,?)",
                           (fecha, f'Gasto: {concepto}', session.get('usuario_nombre','Usuario')))
            asiento_id = cursor.lastrowid
            cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?, 'Gastos Operativos', ?, 0)",
                           (asiento_id, monto))
            cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?, 'Caja', 0, ?)",
                           (asiento_id, monto))
            cursor.execute("INSERT INTO gastos (fecha, concepto, monto_usd, asiento_id) VALUES (?,?,?,?)",
                           (fecha, concepto, monto, asiento_id))
            bd.commit()
            return f"Gasto '{concepto}' por ${monto:.2f} registrado."
        except Exception as e:
            bd.rollback()
            return f"Error: {str(e)}"

    elif intencion == 'tasa':
        return f"Tasa actual: 1 USD = {obtener_tasa():.2f} Bs."

    elif intencion == 'ayuda':
        return "Puedo: vender, consultar stock, agregar producto, ver caja, registrar gasto, ver tasa. Di 'ayuda' para más."

    else:
        return "No entendí. Di 'ayuda' para ver opciones."

@api_bp.route('/api/chatbot', methods=['POST'])
@login_requerido
@negocio_requerido
def chatbot_api():
    data = request.get_json()
    pregunta = data.get('pregunta', '').strip()
    if not pregunta:
        return jsonify({'respuesta': 'No te escuché bien. ¿Puedes repetir?'})
    try:
        intencion = detectar_intencion(pregunta)
        entidades = extraer_entidades(pregunta)
        respuesta = ejecutar_intencion(intencion, entidades, pregunta)
    except Exception as e:
        respuesta = f"Ocurrió un error: {str(e)}. Intenta de nuevo."
    return jsonify({'respuesta': respuesta})

# ------------------------------------------------------------------
# ESCANEAR FACTURA POR FOTO (OCR)
# ------------------------------------------------------------------
def extraer_datos_factura(texto):
    lineas = [l.strip() for l in texto.split('\n') if l.strip()]
    productos = []
    total = None
    metodo = None
    for linea in lineas:
        match_total = re.search(r'(?:total|importe)[:\s]*[\$]?\s*(\d+[.,]\d{1,2})', linea, re.IGNORECASE)
        if match_total:
            total = float(match_total.group(1).replace(',', '.'))
        if re.search(r'efectivo', linea, re.IGNORECASE):
            metodo = 'Efectivo USD'
        elif re.search(r'pago\s*m[oó]vil', linea, re.IGNORECASE):
            metodo = 'Pago Móvil'
        elif re.search(r'transferencia', linea, re.IGNORECASE):
            metodo = 'Transferencia'
        match_prod = re.match(r'^(.+?)\s+(\d+)\s+[\$]?\s*(\d+[.,]\d{1,2})$', linea)
        if match_prod:
            productos.append({'descripcion': match_prod.group(1).strip(), 'cantidad': int(match_prod.group(2)), 'precio': float(match_prod.group(3).replace(',', '.'))})
    if not productos and total:
        productos.append({'descripcion': 'Producto escaneado', 'cantidad': 1, 'precio': total})
    return {'productos': productos, 'total': total, 'metodo': metodo or 'Efectivo USD'}

@api_bp.route('/escanear_factura', methods=['GET', 'POST'])
@login_requerido
@negocio_requerido
@rol_requerido(['encargado', 'vendedor'])
def escanear_factura():
    if request.method == 'POST':
        texto = request.form.get('texto_ocr', '').strip()
        if not texto:
            flash('No se detectó texto en la imagen.', 'warning')
            return redirect(url_for('api.escanear_factura'))
        datos = extraer_datos_factura(texto)
        return render_template('escanear_factura.html', modo_prueba=session.get('modo_prueba', False), datos_extraidos=datos)
    return render_template('escanear_factura.html', modo_prueba=session.get('modo_prueba', False), datos_extraidos=None)

@api_bp.route('/registrar_factura_escaneada', methods=['POST'])
@login_requerido
@negocio_requerido
@rol_requerido(['encargado', 'vendedor'])
def registrar_factura_escaneada():
    cliente = request.form.get('cliente', 'Consumidor Final')
    metodo_pago = request.form.get('metodo_pago', 'Efectivo USD')
    productos = json.loads(request.form.get('productos_json', '[]'))
    if not productos:
        flash('No hay productos para registrar.', 'danger')
        return redirect(url_for('api.escanear_factura'))
    bd = obtener_bd()
    cursor = bd.cursor()
    fecha_venta = datetime.now().strftime('%Y-%m-%d')
    tasa_venta = obtener_tasa_por_fecha(fecha_venta)
    total_venta = 0.0
    total_costo = 0.0
    detalles = []
    bd.execute("BEGIN")
    try:
        for prod in productos:
            desc = prod.get('descripcion', 'Producto').strip()
            cant = int(prod.get('cantidad', 1))
            precio = float(prod.get('precio', 0))
            total_venta += cant * precio
            prod_db = cursor.execute("SELECT sku, costo_usd, stock FROM productos WHERE lower(descripcion) = lower(?)", (desc,)).fetchone()
            if prod_db:
                sku = prod_db['sku']
                costo = prod_db['costo_usd']
                if prod_db['stock'] < cant:
                    raise ValueError(f"Stock insuficiente para {desc}")
                cursor.execute("UPDATE productos SET stock = stock - ? WHERE sku = ?", (cant, sku))
            else:
                sku = generar_sku_sugerido()
                costo = precio * 0.6
                cursor.execute("INSERT INTO productos (sku, descripcion, costo_usd, stock) VALUES (?,?,?,0)", (sku, desc, costo))
            total_costo += costo * cant
            detalles.append((sku, cant, precio))

        comision_pct = obtener_comision()
        monto_comision = total_venta * (comision_pct / 100)
        total_final = total_venta + monto_comision
        num_factura = obtener_siguiente_numero_factura_con_cursor(cursor)

        cursor.execute("INSERT INTO asientos (fecha, concepto, referencia, usuario, numero_factura, tasa_usada) VALUES (?,?,?,?,?,?)",
                       (fecha_venta, f"Venta escaneada - {cliente}", "OCR", session.get('usuario_nombre','Usuario'), num_factura, tasa_venta))
        asiento_id = cursor.lastrowid
        cuenta_ingreso = f"Caja {metodo_pago}"

        cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,?,0)", (asiento_id, cuenta_ingreso, total_final))
        cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,0,?)", (asiento_id, "Ingresos por Ventas", total_venta))
        if monto_comision > 0:
            cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,?,0)", (asiento_id, "Comisión Sistema", monto_comision))
            cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,0,?)", (asiento_id, "Ingresos por Comisión", monto_comision))
        cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,?,0)", (asiento_id, "Costo de Ventas", total_costo))
        cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,0,?)", (asiento_id, "Inventario de Mercancía", total_costo))
        cursor.execute("INSERT INTO facturas (numero, fecha, cliente, total_usd, metodo_pago, asiento_id) VALUES (?,?,?,?,?,?)",
                       (num_factura, fecha_venta, cliente, total_final, metodo_pago, asiento_id))
        for det in detalles:
            cursor.execute("INSERT INTO venta_detalle (factura_numero, sku, cantidad, precio_unitario_usd) VALUES (?,?,?,?)",
                           (num_factura, det[0], det[1], det[2]))
        bd.commit()
        registrar_log("Factura escaneada", session['usuario_id'], f"Factura {num_factura}")
        flash(f"Factura escaneada registrada: {num_factura}", "success")
        return redirect(url_for('ventas.ver_factura', num=num_factura))
    except Exception as e:
        bd.rollback()
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('api.escanear_factura'))
