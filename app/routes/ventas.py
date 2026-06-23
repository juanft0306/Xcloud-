from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime
import sqlite3
from app.db.sqlite import obtener_bd
from app.utils.tasas import obtener_tasa, obtener_tasa_por_fecha, obtener_comision
from app.utils.logs import registrar_log
from app.utils.decoradores import login_requerido, negocio_requerido, rol_requerido
from app.config import Config

ventas_bp = Blueprint('ventas', __name__)

# ------------------------------------------------------------------
# FUNCIONES AUXILIARES
# ------------------------------------------------------------------
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

def anular_factura(numero):
    bd = obtener_bd()
    cursor = bd.cursor()
    factura = cursor.execute("SELECT * FROM facturas WHERE numero=?", (numero,)).fetchone()
    if not factura:
        return False, "Factura no encontrada"
    asiento_id = factura['asiento_id']
    detalle = cursor.execute("SELECT sku, cantidad FROM venta_detalle WHERE factura_numero=?", (numero,)).fetchall()
    bd.execute("BEGIN")
    try:
        for item in detalle:
            cursor.execute("UPDATE productos SET stock = stock + ? WHERE sku=?", (item['cantidad'], item['sku']))
        cursor.execute("DELETE FROM movimientos WHERE asiento_id=?", (asiento_id,))
        cursor.execute("DELETE FROM asientos WHERE id=?", (asiento_id,))
        cursor.execute("DELETE FROM venta_detalle WHERE factura_numero=?", (numero,))
        cursor.execute("DELETE FROM facturas WHERE numero=?", (numero,))
        bd.commit()
        registrar_log("Anulación de factura", session['usuario_id'], f"Factura {numero}")
        return True, f"Factura {numero} anulada."
    except Exception as e:
        bd.rollback()
        return False, f"Error: {str(e)}"

# ------------------------------------------------------------------
# PUNTO DE VENTA
# ------------------------------------------------------------------
@ventas_bp.route('/venta', methods=['GET', 'POST'])
@login_requerido
@negocio_requerido
@rol_requerido(['encargado', 'vendedor'])
def punto_venta():
    bd = obtener_bd()
    cursor = bd.cursor()
    if request.method == 'POST':
        cliente = request.form.get('cliente', 'Consumidor Final')
        metodo_pago = request.form.get('metodo_pago')
        skus = request.form.getlist('sku[]')
        cantidades = request.form.getlist('cantidad[]')
        precios_manual = request.form.getlist('precio[]')
        fecha_venta = request.form.get('fecha_venta', datetime.now().strftime('%Y-%m-%d'))
        tasa_venta = obtener_tasa_por_fecha(fecha_venta)
        monto_recibido = float(request.form.get('monto_recibido', '0') or 0)
        gasto_concepto = request.form.get('gasto_concepto', '').strip()
        gasto_monto = float(request.form.get('gasto_monto', '0') or 0)

        if not skus:
            flash("Agregue productos", "warning")
            return redirect(url_for('ventas.punto_venta'))

        bd.execute("BEGIN")
        try:
            total_venta = 0.0
            total_costo = 0.0
            detalles = []
            for idx, sku in enumerate(skus):
                cant = int(cantidades[idx])
                precio = float(precios_manual[idx])
                total_venta += cant * precio
                prod = cursor.execute("SELECT costo_usd, descripcion, stock FROM productos WHERE sku = ?", (sku,)).fetchone()
                if not prod or prod['stock'] < cant:
                    raise ValueError(f"Stock insuficiente para {sku}")
                total_costo += prod['costo_usd'] * cant
                detalles.append((sku, cant, precio))
                cursor.execute("UPDATE productos SET stock = stock - ? WHERE sku = ?", (cant, sku))

            comision_pct = obtener_comision()
            monto_comision = total_venta * (comision_pct / 100)
            total_final = total_venta + monto_comision
            total_con_gastos = total_final + gasto_monto

            if monto_recibido < total_con_gastos:
                raise ValueError(f"Monto recibido (${monto_recibido:.2f}) insuficiente. Total + gastos: ${total_con_gastos:.2f}")

            vuelto = monto_recibido - total_con_gastos
            num_factura = obtener_siguiente_numero_factura_con_cursor(cursor)

            cursor.execute("INSERT INTO asientos (fecha, concepto, referencia, usuario, numero_factura, tasa_usada) VALUES (?,?,?,?,?,?)",
                           (fecha_venta, f"Venta - {cliente}", "POS", session.get('usuario_nombre','Usuario'), num_factura, tasa_venta))
            asiento_id = cursor.lastrowid
            cuenta = f"Caja {metodo_pago}"

            cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,?,0)", (asiento_id, cuenta, monto_recibido))
            if vuelto > 0:
                cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,0,?)", (asiento_id, cuenta, vuelto))

            cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,0,?)", (asiento_id, "Ingresos por Ventas", total_venta))

            if monto_comision > 0:
                cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,?,0)", (asiento_id, "Comisión Sistema", monto_comision))
                cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,0,?)", (asiento_id, "Ingresos por Comisión", monto_comision))

            if gasto_monto > 0 and gasto_concepto:
                cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,?,0)", (asiento_id, "Gastos Operativos", gasto_monto))
                cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,0,?)", (asiento_id, cuenta, gasto_monto))
                cursor.execute("INSERT INTO gastos (fecha, concepto, monto_usd, categoria, asiento_id) VALUES (?,?,?,?,?)",
                               (fecha_venta, gasto_concepto, gasto_monto, 'Venta', asiento_id))

            cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,?,0)", (asiento_id, "Costo de Ventas", total_costo))
            cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,0,?)", (asiento_id, "Inventario de Mercancía", total_costo))

            cursor.execute("INSERT INTO facturas (numero, fecha, cliente, total_usd, metodo_pago, asiento_id) VALUES (?,?,?,?,?,?)",
                           (num_factura, fecha_venta, cliente, total_final, metodo_pago, asiento_id))
            for det in detalles:
                cursor.execute("INSERT INTO venta_detalle (factura_numero, sku, cantidad, precio_unitario_usd) VALUES (?,?,?,?)",
                               (num_factura, det[0], det[1], det[2]))

            bd.commit()
            registrar_log("Venta registrada", session['usuario_id'], f"Factura {num_factura}")
            flash(f"Venta exitosa. Factura: {num_factura}", "success")
            if vuelto > 0:
                flash(f"Vuelto: ${vuelto:.2f}", "info")
            if gasto_monto > 0:
                flash(f"Gasto registrado: {gasto_concepto} por ${gasto_monto:.2f}", "info")
            return redirect(url_for('ventas.punto_venta'))
        except Exception as e:
            bd.rollback()
            flash(f"Error: {str(e)}", "danger")
            return redirect(url_for('ventas.punto_venta'))

    productos = cursor.execute("SELECT sku, descripcion, costo_usd, stock FROM productos WHERE stock > 0 ORDER BY descripcion").fetchall()
    return render_template('punto_venta.html', productos=productos, modo_prueba=session.get('modo_prueba', False))

# ------------------------------------------------------------------
# LISTAR FACTURAS
# ------------------------------------------------------------------
@ventas_bp.route('/facturas', methods=['GET', 'POST'])
@login_requerido
@negocio_requerido
@rol_requerido(['encargado', 'vendedor'])
def listar_facturas():
    bd = obtener_bd()
    cursor = bd.cursor()

    if request.method == 'POST' and session.get('rol_activo') == 'encargado':
        tipo = request.form.get('tipo_factura', 'moderna')
        if tipo in ('moderna', 'clasica'):
            cursor.execute("INSERT OR REPLACE INTO configuraciones (clave, valor) VALUES ('tipo_factura', ?)", (tipo,))
            bd.commit()
            flash(f'Diseño de factura cambiado a {"Moderna" if tipo=="moderna" else "Clásica"}.', 'success')

    cursor.execute("SELECT valor FROM configuraciones WHERE clave='tipo_factura'")
    tipo_actual = (cursor.fetchone() or ['moderna'])[0]

    filtro_cliente = request.args.get('cliente', '').strip()
    filtro_metodo = request.args.get('metodo', '').strip()
    filtro_fecha = request.args.get('fecha', '').strip()
    pagina = request.args.get('pagina', 1, type=int)
    por_pagina = 20

    query = "SELECT * FROM facturas WHERE 1=1"
    params = []
    if filtro_cliente:
        query += " AND cliente LIKE ?"
        params.append(f'%{filtro_cliente}%')
    if filtro_metodo:
        query += " AND metodo_pago = ?"
        params.append(filtro_metodo)
    if filtro_fecha:
        query += " AND fecha = ?"
        params.append(filtro_fecha)

    total = cursor.execute(f"SELECT COUNT(*) FROM ({query})", params).fetchone()[0]
    query += " ORDER BY fecha DESC LIMIT ? OFFSET ?"
    params.extend([por_pagina, (pagina - 1) * por_pagina])
    facturas = cursor.execute(query, params).fetchall()
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)

    return render_template('facturas.html',
                           facturas=facturas,
                           pagina=pagina,
                           total_paginas=total_paginas,
                           filtro_cliente=filtro_cliente,
                           filtro_metodo=filtro_metodo,
                           filtro_fecha=filtro_fecha,
                           tipo_actual=tipo_actual,
                           modo_prueba=session.get('modo_prueba', False))

# ------------------------------------------------------------------
# VER FACTURA
# ------------------------------------------------------------------
@ventas_bp.route('/facturas/<int:num>')
@login_requerido
@negocio_requerido
def ver_factura(num):
    bd = obtener_bd()
    cursor = bd.cursor()
    factura = cursor.execute("SELECT * FROM facturas WHERE numero=?", (num,)).fetchone()
    if not factura:
        flash("Factura no encontrada", "danger")
        return redirect(url_for('ventas.listar_facturas'))

    asiento = cursor.execute("SELECT tasa_usada FROM asientos WHERE id=?", (factura['asiento_id'],)).fetchone()
    tasa = asiento['tasa_usada'] if asiento else obtener_tasa()
    cursor.execute("SELECT valor FROM configuraciones WHERE clave='tipo_factura'")
    tipo = cursor.fetchone()
    tipo_factura = tipo['valor'] if tipo else 'moderna'

    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT nombre, telefono, email FROM negocios WHERE id=?", (session['negocio_id'],))
        negocio = c.fetchone()
    datos = {'nombre': negocio[0] if negocio else 'Negocio',
             'telefono': negocio[1] if negocio and negocio[1] else '',
             'email': negocio[2] if negocio and negocio[2] else ''}

    comision_pct = obtener_comision()

    if tipo_factura == 'clasica':
        detalles = cursor.execute("SELECT sku, cantidad, precio_unitario_usd FROM venta_detalle WHERE factura_numero=?", (num,)).fetchall()
        return render_template('factura_clasica.html', factura=factura, detalles=detalles, tasa=tasa, negocio=datos, comision_pct=comision_pct)
    else:
        return render_template('factura_detalle.html', factura=factura, tasa=tasa, negocio=datos, comision_pct=comision_pct)

# ------------------------------------------------------------------
# ANULAR FACTURA
# ------------------------------------------------------------------
@ventas_bp.route('/facturas/anular/<int:num>')
@login_requerido
@negocio_requerido
@rol_requerido(['encargado'])
def anular_factura_ruta(num):
    ok, mensaje = anular_factura(num)
    flash(mensaje, 'success' if ok else 'danger')
    return redirect(url_for('ventas.listar_facturas'))
