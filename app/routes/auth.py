from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
import random
import secrets
from app.db.sqlite import obtener_bd
from app.utils.seguridad import generar_password
from app.utils.logs import registrar_log, registrar_intento_fallido, intentos_fallidos, crear_notificacion
from app.utils.decoradores import login_requerido

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/')
def portal():
    if 'usuario_id' in session:
        if session.get('rol') == 'programador':
            return redirect(url_for('dashboard.seleccionar_negocio'))
        if session.get('negocio_id'):
            return redirect(url_for('dashboard.dashboard_negocio'))
        session.clear()
        flash('No se encontró un negocio activo. Inicia sesión de nuevo.', 'warning')
    return render_template('portal.html')

@auth_bp.route('/login_programador', methods=['POST'])
def login_programador():
    from app.config import Config
    import sqlite3
    email = request.form['email']
    password = request.form['password']
    if intentos_fallidos(email) >= 5:
        flash('Demasiados intentos fallidos. Espere 15 minutos.', 'danger')
        return redirect(url_for('auth.portal'))
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT id, nombre, rol, activo, negocio_id, password FROM usuarios WHERE email=? AND rol='programador'", (email,))
        user = c.fetchone()
    if user and check_password_hash(user[5], password):
        if user[3] != 1:
            flash('Cuenta de programador inactiva.', 'danger')
            return redirect(url_for('auth.portal'))
        session['usuario_id'] = user[0]
        session['usuario_nombre'] = user[1]
        session['rol'] = user[2]
        session['negocio_id'] = None
        registrar_log("Inicio sesión programador", user[0])
        return redirect(url_for('dashboard.seleccionar_negocio'))
    else:
        registrar_intento_fallido(email)
        flash('Credenciales incorrectas', 'danger')
        return redirect(url_for('auth.portal'))

@auth_bp.route('/login_negocio', methods=['POST'])
def login_negocio():
    from app.config import Config
    import sqlite3
    from datetime import datetime, timedelta
    email_negocio = request.form['email_negocio']
    password_negocio = request.form['password_negocio']
    if intentos_fallidos(email_negocio) >= 5:
        flash('Demasiados intentos fallidos. Espere 15 minutos.', 'danger')
        return redirect(url_for('auth.portal'))
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT id, nombre, password, estado, licencia_activa FROM negocios WHERE email=?", (email_negocio,))
        negocio = c.fetchone()
        if not negocio:
            registrar_intento_fallido(email_negocio)
            flash('Credenciales de negocio incorrectas', 'danger')
            return redirect(url_for('auth.portal'))
        if negocio[3] != 'aprobado':
            flash('Negocio no aprobado aún.', 'warning')
            return redirect(url_for('auth.portal'))
        if negocio[4] == 0:
            flash('Licencia desactivada. Contacte al programador.', 'warning')
            return redirect(url_for('auth.portal'))
        if check_password_hash(negocio[2], password_negocio):
            session['negocio_id'] = negocio[0]
            session['negocio_nombre'] = negocio[1]
            c.execute("SELECT fecha_proximo_pago, activa, periodicidad FROM suscripciones WHERE negocio_id=?", (negocio[0],))
            susc = c.fetchone()
            if susc and susc[1]:
                hoy = datetime.now()
                periodicidad = susc[2] or 'mensual'
                delta = {'diario': timedelta(days=1), 'semanal': timedelta(weeks=1), 'mensual': timedelta(days=30), 'anual': timedelta(days=365)}.get(periodicidad, timedelta(days=30))
                fecha_limite = datetime.strptime(susc[0], '%Y-%m-%d') if susc[0] else hoy
                if hoy > fecha_limite + delta:
                    flash('Suscripción vencida. Contacte al programador.', 'warning')
                    return redirect(url_for('auth.portal'))
            registrar_log("Inicio sesión negocio", None, f"Negocio {negocio[0]}")
            return redirect(url_for('dashboard.seleccionar_rol_personal'))
        else:
            registrar_intento_fallido(email_negocio)
            flash('Credenciales incorrectas', 'danger')
            return redirect(url_for('auth.portal'))

@auth_bp.route('/registro_negocio', methods=['GET', 'POST'])
def registro_negocio():
    from app.config import Config
    import sqlite3
    if request.method == 'POST':
        nombre_negocio = request.form['nombre_negocio']
        telefono = request.form['telefono']
        descripcion = request.form['descripcion']
        email_encargado = request.form['email_encargado']
        sufijo = random.randint(1000, 9999)
        email_negocio = f"{nombre_negocio.lower().replace(' ', '_')}_{sufijo}@empresa.com"
        password_negocio = generar_password()
        password_encargado = generar_password()
        with sqlite3.connect(Config.BD_SISTEMA) as conn:
            c = conn.cursor()
            if c.execute("SELECT id FROM negocios WHERE email=?", (email_negocio,)).fetchone():
                flash('Ya existe un negocio con ese nombre', 'danger')
                return redirect(url_for('auth.registro_negocio'))
            fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute('''INSERT INTO solicitudes (nombre_negocio, email, telefono, descripcion, password,
                         fecha_solicitud, estado, encargado_email, encargado_password)
                         VALUES (?,?,?,?,?,?,?,?,?)''',
                      (nombre_negocio, email_negocio, telefono, descripcion,
                       generate_password_hash(password_negocio), fecha, 'pendiente',
                       email_encargado, generate_password_hash(password_encargado)))
        registrar_log("Solicitud de registro", None, f"Negocio: {nombre_negocio}")
        flash('Solicitud enviada. Espera la validación del programador.', 'success')
        return redirect(url_for('auth.portal'))
    return render_template('registro_negocio.html')

@auth_bp.route('/cerrar_sesion')
def cerrar_sesion():
    from app.config import Config
    import os
    if session.get('negocio_id') == 'verificacion':
        if os.path.exists(Config.BD_VERIFICACION):
            os.remove(Config.BD_VERIFICACION)
    registrar_log("Cierre de sesión", session.get('usuario_id'))
    session.clear()
    flash('Sesión cerrada', 'info')
    return redirect(url_for('auth.portal'))

@auth_bp.route('/acceso/<token>')
def acceso_directo(token):
    from app.config import Config
    import sqlite3
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT id, nombre, rol, negocio_id FROM usuarios WHERE access_token=?", (token,))
        usuario = c.fetchone()
        if not usuario:
            flash('Link de acceso no válido.', 'danger')
            return redirect(url_for('auth.portal'))
        session['usuario_id'] = usuario['id']
        session['usuario_nombre'] = usuario['nombre']
        session['rol'] = usuario['rol']
        session['negocio_id'] = usuario['negocio_id']
        session['rol_activo'] = usuario['rol']
    registrar_log("Acceso directo por token", usuario['id'])
    flash(f'Bienvenido {usuario["nombre"]}. Has ingresado como {usuario["rol"]}.', 'success')
    return redirect(url_for('dashboard.dashboard_negocio'))
