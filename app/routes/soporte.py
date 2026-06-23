from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime
import sqlite3
from app.db.sqlite import obtener_bd
from app.utils.logs import registrar_log
from app.utils.decoradores import login_requerido, negocio_requerido, rol_requerido
from app.config import Config

soporte_bp = Blueprint('soporte', __name__)

# ------------------------------------------------------------------
# AYUDA UNIFICADA (manual + info sistema + tickets + notificaciones)
# ------------------------------------------------------------------
@soporte_bp.route('/ayuda')
@login_requerido
def ayuda():
    rol = session.get('rol_activo', 'cliente')
    
    # Manual según rol
    if rol == 'programador':
        manual_html = """<h2>&#128295; Manual del Programador</h2>
        <ul>
            <li><strong>Validar solicitudes:</strong> Aprueba o rechaza nuevos negocios.</li>
            <li><strong>Gestionar negocios:</strong> Lista, elimina y reactiva.</li>
            <li><strong>Licencias:</strong> Activa/desactiva acceso.</li>
            <li><strong>Comisión:</strong> 0-5% sobre ventas.</li>
            <li><strong>Suscripciones:</strong> Configura periodicidad, método de cobro y moneda.</li>
            <li><strong>Tickets:</strong> Responde consultas de soporte.</li>
        </ul>"""
    elif rol == 'encargado':
        manual_html = """<h2>&#128084; Manual del Encargado</h2>
        <ul>
            <li><strong>Dashboard:</strong> Tasa, inventario, ventas, alertas.</li>
            <li><strong>Inventario:</strong> Añadir, actualizar, eliminar productos.</li>
            <li><strong>Ventas:</strong> Punto de venta, facturación.</li>
            <li><strong>Contabilidad:</strong> Balance, resultados, gastos.</li>
            <li><strong>Tasas:</strong> Establecer tasa del día.</li>
            <li><strong>Configuración:</strong> Editar negocio, crear usuarios, permisos.</li>
        </ul>"""
    elif rol == 'vendedor':
        manual_html = """<h2>&#128722; Manual del Vendedor</h2>
        <ul>
            <li><strong>Punto de venta:</strong> Buscar productos, armar carritos, procesar ventas.</li>
            <li><strong>Facturas:</strong> Consultar facturas emitidas.</li>
        </ul>"""
    elif rol == 'cliente':
        manual_html = """<h2>&#128722;&#65039; Manual del Cliente</h2>
        <ul>
            <li><strong>Tienda virtual:</strong> Ver productos, añadir al carrito, realizar pedidos.</li>
            <li><strong>Mis pedidos:</strong> Historial y estado de pedidos.</li>
            <li><strong>Código de entrega:</strong> Comparte el código con el repartidor.</li>
        </ul>"""
    elif rol == 'proveedor':
        manual_html = """<h2>&#128230; Manual del Proveedor</h2>
        <ul>
            <li><strong>Pedidos:</strong> Ver pendientes, verificar entrega con código, rechazar.</li>
        </ul>"""
    else:
        manual_html = "<p>No hay manual disponible para este rol.</p>"

    # Información del sistema
    info_sistema_html = """
    <h2>&#128187; Información del Sistema</h2>
    <h3>&#128274; Seguridad</h3>
    <ul>
        <li><strong>Autenticación:</strong> Contraseñas cifradas con SHA-256.</li>
        <li><strong>Protección de sesiones:</strong> Cookies seguras firmadas.</li>
        <li><strong>Control de acceso:</strong> Roles y permisos específicos.</li>
        <li><strong>Protección contra fuerza bruta:</strong> Bloqueo tras 5 intentos fallidos.</li>
        <li><strong>Tokens de acceso:</strong> Enlaces únicos para acceso directo.</li>
        <li><strong>Códigos de verificación:</strong> 5 caracteres para entrega de pedidos.</li>
    </ul>
    <h3>&#128736;&#65039; Funciones principales</h3>
    <ul>
        <li><strong>Gestión de inventario:</strong> Productos con SKU, costo, stock, imágenes.</li>
        <li><strong>Punto de venta:</strong> Ventas con cálculo de vuelto, múltiples métodos.</li>
        <li><strong>Tienda virtual:</strong> Clientes realizan pedidos con carrito.</li>
        <li><strong>Facturación:</strong> Formato moderno o clásico, descarga como imagen.</li>
        <li><strong>Contabilidad:</strong> Balance general, estado de resultados, gastos.</li>
        <li><strong>Suscripciones:</strong> Cobro recurrente configurable.</li>
        <li><strong>Comisión por venta:</strong> 0% a 5% configurable.</li>
        <li><strong>Asistente virtual Luz:</strong> Chatbot con comandos de voz y texto.</li>
        <li><strong>Escáner de facturas:</strong> Captura por foto con OCR.</li>
        <li><strong>Exportación:</strong> CSV de productos, facturas y contabilidad.</li>
    </ul>
    """

    # Tickets del usuario
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT id, asunto, estado, fecha, respuesta FROM tickets WHERE usuario_id=? ORDER BY fecha DESC LIMIT 10",
                  (session['usuario_id'],))
        tickets = c.fetchall()
        c.execute("SELECT id, mensaje, fecha, leida FROM notificaciones WHERE usuario_id=? ORDER BY fecha DESC LIMIT 20",
                  (session['usuario_id'],))
        notificaciones = c.fetchall()

    return render_template('ayuda.html',
                           manual_html=manual_html,
                           info_sistema_html=info_sistema_html,
                           tickets=tickets,
                           notificaciones=notificaciones)

# ------------------------------------------------------------------
# SOPORTE (tickets) - formulario y listado
# ------------------------------------------------------------------
@soporte_bp.route('/soporte', methods=['GET', 'POST'])
@login_requerido
@negocio_requerido
def soporte():
    if request.method == 'POST':
        asunto = request.form.get('asunto', '').strip()
        mensaje = request.form.get('mensaje', '').strip()
        if not asunto or not mensaje:
            flash('Asunto y mensaje son obligatorios.', 'danger')
        else:
            with sqlite3.connect(Config.BD_SISTEMA) as conn:
                conn.execute("INSERT INTO tickets (negocio_id, usuario_id, asunto, mensaje, fecha) VALUES (?,?,?,?,?)",
                             (session['negocio_id'], session['usuario_id'], asunto, mensaje,
                              datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            registrar_log("Ticket enviado", session['usuario_id'], f"Asunto: {asunto}")
            flash('Ticket enviado. El programador te responderá pronto.', 'success')
            return redirect(url_for('dashboard.dashboard_negocio'))
    
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT id, asunto, estado, fecha, respuesta FROM tickets WHERE usuario_id=? ORDER BY fecha DESC",
                  (session['usuario_id'],))
        tickets = c.fetchall()
    return render_template('soporte.html', tickets=tickets)

# ------------------------------------------------------------------
# VER LOGS (actividad del sistema)
# ------------------------------------------------------------------
@soporte_bp.route('/ver_logs')
@login_requerido
def ver_logs():
    if session.get('rol_activo') not in ['encargado', 'proveedor'] and session.get('rol') != 'programador':
        flash('No tienes permiso para ver los logs.', 'danger')
        return redirect(url_for('dashboard.dashboard_negocio'))
    
    pagina = request.args.get('pagina', 1, type=int)
    por_pagina = 30
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        total = c.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
        logs = c.execute("SELECT fecha, usuario_id, accion, detalles FROM logs ORDER BY id DESC LIMIT ? OFFSET ?",
                         (por_pagina, (pagina-1)*por_pagina)).fetchall()
        total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
    return render_template('ver_logs.html', logs=logs, pagina=pagina, total_paginas=total_paginas)

# ------------------------------------------------------------------
# NOTIFICACIONES
# ------------------------------------------------------------------
@soporte_bp.route('/notificaciones')
@login_requerido
def ver_notificaciones():
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT id, mensaje, fecha, leida FROM notificaciones WHERE usuario_id=? ORDER BY fecha DESC",
                  (session['usuario_id'],))
        notificaciones = c.fetchall()
    return render_template('ver_notificaciones.html', notificaciones=notificaciones)

@soporte_bp.route('/notificaciones/<int:notificacion_id>/leida')
@login_requerido
def marcar_leida(notificacion_id):
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        conn.execute("UPDATE notificaciones SET leida=1 WHERE id=? AND usuario_id=?",
                     (notificacion_id, session['usuario_id']))
    return redirect(url_for('soporte.ver_notificaciones'))

# ------------------------------------------------------------------
# MI CUENTA (perfil de usuario)
# ------------------------------------------------------------------
@soporte_bp.route('/mi_cuenta', methods=['GET', 'POST'])
@login_requerido
def mi_cuenta():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        telefono = request.form.get('telefono', '').strip()
        if nombre:
            with sqlite3.connect(Config.BD_SISTEMA) as conn:
                conn.execute("UPDATE usuarios SET nombre=?, telefono=? WHERE id=?",
                             (nombre, telefono, session['usuario_id']))
            session['usuario_nombre'] = nombre
            flash('Datos actualizados.', 'success')
    
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT nombre, telefono, email FROM usuarios WHERE id=?", (session['usuario_id'],))
        usuario = c.fetchone()
        c.execute("SELECT id, fecha_pedido, total_usd, estado FROM pedidos WHERE cliente_id=? ORDER BY fecha_pedido DESC LIMIT 10",
                  (session['usuario_id'],))
        pedidos = c.fetchall()
    return render_template('mi_cuenta.html', usuario=usuario, pedidos=pedidos)

# ------------------------------------------------------------------
# ESTADÍSTICAS
# ------------------------------------------------------------------
@soporte_bp.route('/estadisticas')
@login_requerido
@negocio_requerido
def estadisticas():
    bd = obtener_bd()
    cursor = bd.cursor()
    
    # Top 10 productos más vendidos
    top = cursor.execute('''SELECT p.sku, p.descripcion, SUM(vd.cantidad * vd.precio_unitario_usd) as total, SUM(vd.cantidad) as unidades
                           FROM venta_detalle vd JOIN productos p ON vd.sku = p.sku GROUP BY vd.sku ORDER BY total DESC LIMIT 10''').fetchall()
    
    # Producto menos vendido
    menos = cursor.execute('''SELECT p.sku, p.descripcion, COALESCE(SUM(vd.cantidad),0) as unidades
                              FROM productos p LEFT JOIN venta_detalle vd ON p.sku = vd.sku
                              GROUP BY p.sku ORDER BY unidades ASC LIMIT 1''').fetchone()
    
    # Método de pago más frecuente
    uso = {}
    for m in ['Efectivo', 'Pago Móvil', 'Transferencia']:
        uso[m] = cursor.execute("SELECT COUNT(*) FROM movimientos WHERE cuenta LIKE ? AND debe>0", (f'Caja {m}%',)).fetchone()[0]
    metodo_frec = max(uso, key=uso.get) if uso else "Ninguno"
    
    # Método de pago con mayor monto
    metodo_monto = cursor.execute("SELECT SUBSTR(cuenta,6), SUM(debe) FROM movimientos WHERE cuenta LIKE 'Caja %' GROUP BY cuenta ORDER BY SUM(debe) DESC LIMIT 1").fetchone()
    
    # Productos con stock bajo (<= 5)
    sugerencias = cursor.execute("SELECT sku, descripcion, stock FROM productos WHERE stock <= 5").fetchall()
    
    return render_template('estadisticas.html',
                           top=top,
                           menos=menos,
                           metodo_frecuente=metodo_frec,
                           metodo_monto=metodo_monto,
                           sugerencias=sugerencias,
                           uso_metodos=uso,
                           modo_prueba=session.get('modo_prueba', False))
