from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime
from app.db.sqlite import obtener_bd
from app.utils.helpers import generar_sku_sugerido
from app.utils.logs import registrar_log
from app.utils.decoradores import login_requerido, negocio_requerido, rol_requerido
from app.config import Config
import os
from werkzeug.utils import secure_filename

inventario_bp = Blueprint('inventario', __name__)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

def eliminar_producto(sku):
    bd = obtener_bd()
    cursor = bd.cursor()
    prod = cursor.execute("SELECT descripcion FROM productos WHERE sku=?", (sku,)).fetchone()
    if not prod:
        return False, "Producto no encontrado"
    usado = cursor.execute("SELECT COUNT(*) FROM venta_detalle WHERE sku=?", (sku,)).fetchone()[0]
    if usado > 0:
        return False, f"No se puede eliminar: tiene {usado} ventas."
    cursor.execute("DELETE FROM productos WHERE sku=?", (sku,))
    bd.commit()
    registrar_log("Eliminación de producto", session['usuario_id'], f"SKU: {sku}")
    return True, f"Producto '{prod['descripcion']}' eliminado."

@inventario_bp.route('/inventario', methods=['GET', 'POST'])
@login_requerido
@negocio_requerido
@rol_requerido(['encargado'])
def inventario():
    bd = obtener_bd()
    cursor = bd.cursor()
    sku_sugerido = generar_sku_sugerido() or "A001"
    
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT tiene_clientes FROM negocios WHERE id=?", (session['negocio_id'],))
        tiene_clientes = (c.fetchone() or [1])[0]

    if request.method == 'POST':
        nombre = request.form['descripcion'].strip()
        if not nombre:
            flash("Descripción obligatoria", "danger")
            return redirect(url_for('inventario.inventario'))
        
        cursor.execute("SELECT sku FROM productos WHERE lower(descripcion) = lower(?)", (nombre,))
        existente = cursor.fetchone()
        sku = existente['sku'] if existente else request.form['sku'].strip().upper() or generar_sku_sugerido()
        if not sku:
            flash("No hay más SKU disponibles", "danger")
            return redirect(url_for('inventario.inventario'))
        
        try:
            costo = float(request.form['costo'])
            if costo <= 0:
                flash("Costo debe ser mayor que cero", "danger")
                return redirect(url_for('inventario.inventario'))
        except:
            flash("Costo inválido", "danger")
            return redirect(url_for('inventario.inventario'))
        
        moneda = request.form['moneda']
        try:
            stock = int(request.form['stock'])
            if stock < 0:
                flash("Stock no puede ser negativo", "danger")
                return redirect(url_for('inventario.inventario'))
        except:
            flash("Stock inválido", "danger")
            return redirect(url_for('inventario.inventario'))
        
        limite = int(request.form.get('limite_critico', 0))
        fecha_compra = request.form.get('fecha_compra', datetime.now().strftime('%Y-%m-%d'))
        
        from app.utils.tasas import obtener_tasa_por_fecha
        tasa = obtener_tasa_por_fecha(fecha_compra)
        costo_usd = costo / tasa if moneda == 'VES' and tasa > 0 else costo

        imagen_url = ''
        if tiene_clientes:
            if 'imagen' in request.files:
                file = request.files['imagen']
                if file and file.filename != '' and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    nombre_archivo = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], nombre_archivo))
                    imagen_url = f"/static/uploads/{nombre_archivo}"
            if not imagen_url:
                imagen_url = request.form.get('imagen_url', '')

        try:
            cursor.execute('''INSERT INTO productos (sku, descripcion, costo_usd, stock, limite_critico, imagen_url)
                              VALUES (?,?,?,?,?,?) ON CONFLICT(sku) DO UPDATE SET
                              descripcion=excluded.descripcion, costo_usd=excluded.costo_usd,
                              stock=stock+excluded.stock, limite_critico=excluded.limite_critico, imagen_url=excluded.imagen_url''',
                           (sku, nombre, costo_usd, stock, limite, imagen_url))
            bd.commit()
            registrar_log("Producto guardado", session['usuario_id'], f"SKU: {sku}")
            flash(f"Producto guardado con SKU {sku}", "success")
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('inventario.inventario'))

    # GET - listar productos con paginación y búsqueda
    busqueda = request.args.get('busqueda', '').strip()
    pagina = request.args.get('pagina', 1, type=int)
    por_pagina = 20
    query = "SELECT sku, descripcion, costo_usd, stock, limite_critico, imagen_url FROM productos"
    params = []
    if busqueda:
        query += " WHERE sku LIKE ? OR descripcion LIKE ?"
        params.extend([f'%{busqueda}%', f'%{busqueda}%'])
    
    total_productos = cursor.execute(f"SELECT COUNT(*) FROM productos" + (f" WHERE sku LIKE ? OR descripcion LIKE ?" if busqueda else ""), params if busqueda else []).fetchone()[0]
    query += " ORDER BY rowid DESC LIMIT ? OFFSET ?"
    params.extend([por_pagina, (pagina-1)*por_pagina])
    productos = cursor.execute(query, params).fetchall()
    total_paginas = max(1, (total_productos + por_pagina - 1) // por_pagina)

    return render_template('inventario.html',
                           productos=productos,
                           sku_sugerido=sku_sugerido,
                           modo_prueba=session.get('modo_prueba', False),
                           tiene_clientes=tiene_clientes,
                           pagina=pagina,
                           total_paginas=total_paginas,
                           busqueda=busqueda)

@inventario_bp.route('/inventario/eliminar/<sku>')
@login_requerido
@negocio_requerido
@rol_requerido(['encargado'])
def eliminar_producto_ruta(sku):
    ok, mensaje = eliminar_producto(sku)
    flash(mensaje, 'success' if ok else 'danger')
    return redirect(url_for('inventario.inventario'))

@inventario_bp.route('/producto/<sku>')
@login_requerido
@negocio_requerido
@rol_requerido(['encargado'])
def detalle_producto(sku):
    bd = obtener_bd()
    cursor = bd.cursor()
    prod = cursor.execute("SELECT * FROM productos WHERE sku=?", (sku,)).fetchone()
    if not prod:
        flash('Producto no encontrado', 'danger')
        return redirect(url_for('inventario.inventario'))
    return render_template('detalle_producto.html', producto=prod)

@inventario_bp.route('/reponer', methods=['POST'])
@login_requerido
@negocio_requerido
@rol_requerido(['encargado'])
def reponer():
    sku = request.form['sku']
    try:
        cantidad = int(request.form['cantidad'])
        if cantidad <= 0:
            flash("Cantidad positiva", "danger")
            return redirect(url_for('inventario.inventario'))
    except:
        flash("Cantidad inválida", "danger")
        return redirect(url_for('inventario.inventario'))
    
    bd = obtener_bd()
    cursor = bd.cursor()
    cursor.execute("UPDATE productos SET stock = stock + ? WHERE sku = ?", (cantidad, sku))
    if cursor.rowcount == 0:
        flash("Producto no encontrado", "danger")
    else:
        bd.commit()
        flash("Stock actualizado", "success")
    return redirect(url_for('inventario.inventario'))
