from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from app.db.sqlite import obtener_bd, crear_base_negocio
from app.utils.seguridad import generar_password
from app.utils.tasas import obtener_comision
from app.utils.logs import registrar_log, crear_notificacion
from app.utils.decoradores import login_requerido, negocio_requerido, rol_requerido
from app.config import Config

programador_bp = Blueprint('programador', __name__)

# ------------------------------------------------------------------
# SOLICITUDES DE NEGOCIO
# ------------------------------------------------------------------
@programador_bp.route('/programador/solicitudes')
@login_requerido
def solicitudes():
    if session.get('rol') != 'programador':
        flash('Acceso denegado', 'danger')
        return redirect(url_for('auth.portal'))
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT id, nombre_negocio, email, telefono, descripcion, fecha_solicitud FROM solicitudes WHERE estado='pendiente' ORDER BY fecha_solicitud DESC")
        solicitudes = c.fetchall()
    return render_template('programador_solicitudes.html', solicitudes=solicitudes)

@programador_bp.route('/programador/aprobar/<int:solicitud_id>')
@login_requerido
def aprobar_negocio(solicitud_id):
    if session.get('rol') != 'programador':
        flash('Acceso denegado', 'danger')
        return redirect(url_for('auth.portal'))
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM solicitudes WHERE id=?", (solicitud_id,))
        sol = c.fetchone()
        if not sol:
            flash('Solicitud no encontrada', 'danger')
            return redirect(url_for('programador.solicitudes'))

        nombre = sol['nombre_negocio']
        email_negocio = sol['email']
        telefono = sol['telefono']
        descripcion = sol['descripcion']
        enc_email = sol['encargado_email'] or email_negocio

        password_negocio_plana = generar_password()
        password_hash_negocio = generate_password_hash(password_negocio_plana)
        enc_pass_plana = generar_password()
        enc_pass_hash = generate_password_hash(enc_pass_plana)

        c.execute("INSERT INTO usuarios (email, nombre, password, telefono, rol, activo, creado_por) VALUES (?,?,?,?,?,?,?)",
                  (enc_email, nombre, enc_pass_hash, telefono, 'encargado', 1, session['usuario_id']))
        encargado_id = c.lastrowid

        c.execute("INSERT INTO negocios (nombre, email, telefono, descripcion, programador_id, encargado_id, fecha_creacion, estado, password) VALUES (?,?,?,?,?,?,?,?,?)",
                  (nombre, email_negocio, telefono, descripcion, session['usuario_id'], encargado_id,
                   datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'aprobado', password_hash_negocio))
        negocio_id = c.lastrowid

        c.execute("UPDATE usuarios SET negocio_id=? WHERE id=?", (negocio_id, encargado_id))
        c.execute("UPDATE solicitudes SET estado='aprobado' WHERE id=?", (solicitud_id,))
        conn.commit()

    crear_base_negocio(Config.BD_NOMBRE_BASE.format(negocio_id))
    registrar_log("Aprobación de negocio", session['usuario_id'], f"Negocio: {nombre}")
    crear_notificacion(encargado_id, f"Tu negocio '{nombre}' ha sido aprobado.")

    flash(f'Negocio {nombre} aprobado.', 'success')
    flash(f'🔑 Contraseña del negocio: {password_negocio_plana}', 'warning')
    flash(f'🔑 Contraseña del encargado: {enc_pass_plana}', 'warning')
    flash('⚠️ Entrega estas contraseñas al encargado. No se volverán a mostrar.', 'info')
    return redirect(url_for('programador.solicitudes'))

@programador_bp.route('/programador/rechazar/<int:solicitud_id>')
@login_requerido
def rechazar_negocio(solicitud_id):
    if session.get('rol') != 'programador':
        flash('Acceso denegado', 'danger')
        return redirect(url_for('auth.portal'))
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        conn.execute("UPDATE solicitudes SET estado='rechazado' WHERE id=?", (solicitud_id,))
    flash('Solicitud rechazada', 'warning')
    return redirect(url_for('programador.solicitudes'))

# ------------------------------------------------------------------
# GESTIONAR NEGOCIOS
# ------------------------------------------------------------------
@programador_bp.route('/programador/negocios')
@login_requerido
def negocios():
    if session.get('rol') != 'programador':
        flash('Acceso denegado', 'danger')
        return redirect(url_for('auth.portal'))
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT id, nombre, email, estado FROM negocios ORDER BY fecha_creacion DESC")
        negocios = c.fetchall()
    return render_template('programador_negocios.html', negocios=negocios)

@programador_bp.route('/programador/eliminar_negocio/<int:negocio_id>')
@login_requerido
def eliminar_negocio(negocio_id):
    if session.get('rol') != 'programador':
        flash('Acceso denegado', 'danger')
        return redirect(url_for('auth.portal'))
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("UPDATE usuarios SET negocio_id = NULL WHERE negocio_id=?", (negocio_id,))
        c.execute("DELETE FROM negocios WHERE id=?", (negocio_id,))
    ruta = Config.BD_NOMBRE_BASE.format(negocio_id)
    if os.path.exists(ruta):
        os.remove(ruta)
    flash('Negocio eliminado', 'success')
    return redirect(url_for('programador.negocios'))

# ------------------------------------------------------------------
# LICENCIAS
# ------------------------------------------------------------------
@programador_bp.route('/programador/licencias')
@login_requerido
def licencias():
    if session.get('rol') != 'programador':
        flash('Acceso denegado', 'danger')
        return redirect(url_for('auth.portal'))
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT id, nombre, email, licencia_activa FROM negocios ORDER BY nombre")
        negocios = c.fetchall()
    return render_template('programador_licencias.html', negocios=negocios)

@programador_bp.route('/programador/licencia/<int:negocio_id>/<accion>')
@login_requerido
def cambiar_licencia(negocio_id, accion):
    if session.get('rol') != 'programador':
        flash('Acceso denegado', 'danger')
        return redirect(url_for('auth.portal'))
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        conn.execute("UPDATE negocios SET licencia_activa=? WHERE id=?", (1 if accion == 'activar' else 0, negocio_id))
    flash('Licencia actualizada.', 'success')
    return redirect(url_for('programador.licencias'))

# ------------------------------------------------------------------
# COMISIÓN
# ------------------------------------------------------------------
@programador_bp.route('/programador/comision', methods=['GET', 'POST'])
@login_requerido
def comision():
    if session.get('rol') != 'programador':
        flash('Acceso denegado', 'danger')
        return redirect(url_for('auth.portal'))
    if request.method == 'POST':
        activa = request.form.get('activa_comision', '0')
        porcentaje_str = request.form.get('porcentaje', '0').replace(',', '.')
        try:
            comision = float(porcentaje_str) if activa == '1' and 0 <= float(porcentaje_str) <= 5 else 0.0
            with sqlite3.connect(Config.BD_SISTEMA) as conn:
                conn.execute("INSERT OR REPLACE INTO config_global (clave, valor) VALUES ('comision', ?)", (str(comision),))
            flash(f'Comisión: {comision}%', 'success')
        except:
            flash('Valor inválido.', 'danger')
        return redirect(url_for('programador.comision'))
    comision_actual = obtener_comision()
    return render_template('programador_comision.html', comision=comision_actual)

# ------------------------------------------------------------------
# SUSCRIPCIONES
# ------------------------------------------------------------------
@programador_bp.route('/programador/suscripciones', methods=['GET', 'POST'])
@login_requerido
def suscripciones():
    if session.get('rol') != 'programador':
        flash('Acceso denegado', 'danger')
        return redirect(url_for('auth.portal'))
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        if request.method == 'POST':
            accion = request.form.get('accion', 'actualizar')
            if accion == 'actualizar':
                negocio_id = request.form.get('negocio_id')
                periodicidad = request.form.get('periodicidad', 'mensual')
                metodo_cobro = request.form.get('metodo_cobro', 'transferencia')
                moneda = request.form.get('moneda', 'USD')
                monto_cobro = float(request.form.get('monto_cobro', 5.0))
                activa = request.form.get('activa', '0')
                if negocio_id:
                    c.execute('''INSERT OR REPLACE INTO suscripciones (negocio_id, periodicidad, metodo_cobro, moneda, monto_cobro, activa, tarifa_mensual)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''', (negocio_id, periodicidad, metodo_cobro, moneda, monto_cobro, activa, monto_cobro))
                    conn.commit()
                    flash('Suscripción actualizada.', 'success')

        c.execute('''SELECT n.id, n.nombre, COALESCE(s.periodicidad,'mensual'), COALESCE(s.metodo_cobro,'transferencia'),
                       COALESCE(s.moneda,'USD'), COALESCE(s.monto_cobro,5.0), COALESCE(s.activa,0)
                       FROM negocios n LEFT JOIN suscripciones s ON n.id = s.negocio_id WHERE n.estado='aprobado' ORDER BY n.nombre''')
        suscripciones = c.fetchall()

    return render_template('programador_suscripciones.html', suscripciones=suscripciones)

# ------------------------------------------------------------------
# TICKETS (SOPORTE)
# ------------------------------------------------------------------
@programador_bp.route('/programador/tickets')
@login_requerido
def tickets():
    if session.get('rol') != 'programador':
        flash('Acceso denegado', 'danger')
        return redirect(url_for('auth.portal'))
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute('''SELECT t.id, n.nombre, u.nombre, t.asunto, t.estado FROM tickets t
                     JOIN negocios n ON t.negocio_id = n.id LEFT JOIN usuarios u ON t.usuario_id = u.id
                     ORDER BY t.estado='abierto' DESC, t.fecha DESC''')
        tickets = c.fetchall()
    return render_template('programador_tickets.html', tickets=tickets)

@programador_bp.route('/programador/ticket/<int:ticket_id>', methods=['GET', 'POST'])
@login_requerido
def responder_ticket(ticket_id):
    if session.get('rol') != 'programador':
        flash('Acceso denegado', 'danger')
        return redirect(url_for('auth.portal'))
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        if request.method == 'POST':
            respuesta = request.form.get('respuesta', '').strip()
            if respuesta:
                c.execute("UPDATE tickets SET respuesta=?, estado='cerrado' WHERE id=?", (respuesta, ticket_id))
                conn.commit()
                flash('Ticket cerrado.', 'success')
            return redirect(url_for('programador.tickets'))
        c.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,))
        ticket = c.fetchone()
    return render_template('programador_responder_ticket.html', ticket=ticket)
