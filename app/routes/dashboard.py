from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime, timedelta
import sqlite3
from app.db.sqlite import obtener_bd
from app.utils.tasas import obtener_tasa, guardar_tasa, obtener_comision
from app.utils.logs import registrar_log
from app.utils.decoradores import login_requerido, negocio_requerido, rol_requerido
from app.config import Config

dashboard_bp = Blueprint('dashboard', __name__)

# ------------------------------------------------------------------
# SELECCIÓN DE NEGOCIO (solo programador)
# ------------------------------------------------------------------
@dashboard_bp.route('/seleccionar_negocio')
@login_requerido
def seleccionar_negocio():
    if session.get('rol') != 'programador':
        return redirect(url_for('dashboard.dashboard_negocio'))
    return render_template('seleccionar_negocio.html')

@dashboard_bp.route('/seleccionar_negocio_propio')
@login_requerido
def seleccionar_negocio_propio():
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM negocios WHERE programador_id=? AND nombre='Negocio del Programador'", (session['usuario_id'],))
        negocio = c.fetchone()
    if negocio:
        session['negocio_id'] = negocio[0]
        session['modo_prueba'] = False
        return redirect(url_for('dashboard.seleccionar_roles'))
    flash('No se encontró tu negocio propio', 'danger')
    return redirect(url_for('dashboard.seleccionar_negocio'))

@dashboard_bp.route('/seleccionar_verificacion')
@login_requerido
def seleccionar_verificacion():
    session['negocio_id'] = 'verificacion'
    session['modo_prueba'] = True
    return redirect(url_for('dashboard.seleccionar_roles'))

@dashboard_bp.route('/seleccionar_roles', methods=['GET', 'POST'])
@login_requerido
def seleccionar_roles():
    if session.get('rol') != 'programador':
        flash('No puedes cambiar de rol', 'danger')
        return redirect(url_for('dashboard.dashboard_negocio'))
    roles = ['encargado', 'vendedor', 'cliente', 'proveedor']
    if request.method == 'POST':
        rol_elegido = request.form.get('rol')
        if rol_elegido not in roles:
            flash('Rol no permitido', 'danger')
            return redirect(url_for('dashboard.seleccionar_roles'))
        session['rol_activo'] = rol_elegido
        flash(f'Rol activo: {rol_elegido}', 'success')
        return redirect(url_for('dashboard.dashboard_negocio'))
    return render_template('seleccionar_roles.html', roles=roles)

@dashboard_bp.route('/seleccionar_rol_personal')
@login_requerido
def seleccionar_rol_personal():
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT rol FROM usuarios WHERE id=?", (session['usuario_id'],))
        user = c.fetchone()
    if user and user[0] == 'encargado':
        session['rol_activo'] = 'encargado'
        bd = obtener_bd()
        cursor = bd.cursor()
        cursor.execute("SELECT valor FROM configuraciones WHERE clave='modo_prueba'")
        modo = cursor.fetchone()
        session['modo_prueba'] = (modo['valor'] == '1') if modo else False
        registrar_log("Inicio sesión como encargado", session['usuario_id'])
        flash('Has ingresado como encargado del negocio.', 'success')
        return redirect(url_for('dashboard.dashboard_negocio'))
    else:
        flash('No se encontró un rol de encargado asociado.', 'danger')
        return redirect(url_for('auth.portal'))

# ------------------------------------------------------------------
# DASHBOARD PRINCIPAL
# ------------------------------------------------------------------
@dashboard_bp.route('/dashboard')
@login_requerido
@negocio_requerido
def dashboard_negocio():
    if 'rol_activo' not in session:
        flash('No has seleccionado un rol.', 'warning')
        return redirect(url_for('auth.portal'))
    bd = obtener_bd()
    cursor = bd.cursor()
    tasa = obtener_tasa()
    inv_total_usd = cursor.execute("SELECT SUM(costo_usd * stock) FROM productos").fetchone()[0] or 0.0
    inv_total_bs = inv_total_usd * tasa
    stock_critico = cursor.execute("SELECT sku, descripcion, stock FROM productos WHERE stock <= limite_critico AND limite_critico > 0").fetchall()
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    ventas_dia_usd = cursor.execute('''SELECT SUM(m.haber) FROM movimientos m JOIN asientos a ON m.asiento_id = a.id
                                       WHERE m.cuenta = 'Ingresos por Ventas' AND a.fecha = ?''', (fecha_hoy,)).fetchone()[0] or 0.0
    ventas_dia_bs = ventas_dia_usd * tasa
    fecha_semana = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    top_clientes = cursor.execute('''SELECT cliente, SUM(total_usd) as total_gastado FROM facturas
                                      WHERE fecha >= ? GROUP BY cliente ORDER BY total_gastado DESC LIMIT 5''', (fecha_semana,)).fetchall()
    nombres_clientes = [row['cliente'] for row in top_clientes]
    montos_clientes = [row['total_gastado'] for row in top_clientes]
    modo = session.get('modo_prueba', False)
    rol_activo = session.get('rol_activo', 'Ninguno')
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT tiene_clientes FROM negocios WHERE id=?", (session['negocio_id'],))
        tiene_clientes = (c.fetchone() or [1])[0]
        c.execute("SELECT COUNT(*) FROM notificaciones WHERE usuario_id=? AND leida=0", (session['usuario_id'],))
        notif_count = c.fetchone()[0]
    return render_template('dashboard.html',
                           inv_total_usd=inv_total_usd, inv_total_bs=inv_total_bs,
                           ventas_dia_usd=ventas_dia_usd, ventas_dia_bs=ventas_dia_bs,
                           stock_critico=stock_critico, nombres_clientes=nombres_clientes,
                           montos_clientes=montos_clientes, modo_prueba=modo, tasa=tasa,
                           rol_activo=rol_activo, tiene_clientes=tiene_clientes, notif_count=notif_count)

@dashboard_bp.route('/toggle_modo_prueba_global', methods=['POST'])
@login_requerido
def toggle_modo_prueba_global():
    session['modo_prueba'] = not session.get('modo_prueba', False)
    return jsonify({'success': True, 'modo_prueba': session['modo_prueba']})

@dashboard_bp.route('/guardar_tasa_manual', methods=['POST'])
@login_requerido
@negocio_requerido
@rol_requerido(['encargado'])
def guardar_tasa_manual():
    data = request.get_json()
    try:
        tasa = float(data['tasa'])
        if tasa <= 0:
            raise ValueError
        guardar_tasa(tasa, datetime.now().strftime('%Y-%m-%d'))
        return jsonify({'success': True, 'tasa': tasa})
    except:
        return jsonify({'success': False, 'error': 'Tasa inválida'})

@dashboard_bp.route('/toggle_tema', methods=['POST'])
@login_requerido
def toggle_tema():
    data = request.get_json()
    if data and 'tema' in data:
        nuevo_tema = data['tema']
    else:
        tema_actual = session.get('tema', 'claro')
        nuevo_tema = 'oscuro' if tema_actual == 'claro' else 'claro'
    session['tema'] = nuevo_tema
    if 'negocio_id' in session and session['negocio_id'] != 'verificacion':
        try:
            bd = obtener_bd()
            bd.execute("INSERT OR REPLACE INTO configuraciones (clave, valor) VALUES ('tema', ?)", (nuevo_tema,))
            bd.commit()
        except:
            pass
    return jsonify({'success': True, 'tema': nuevo_tema})
