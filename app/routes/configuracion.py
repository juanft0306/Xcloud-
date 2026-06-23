from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime
import sqlite3
import random
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from app.db.sqlite import obtener_bd
from app.utils.tasas import obtener_tasa, guardar_tasa, obtener_comision
from app.utils.logs import registrar_log
from app.utils.decoradores import login_requerido, negocio_requerido, rol_requerido
from app.config import Config

configuracion_bp = Blueprint('configuracion', __name__)

@configuracion_bp.route('/configuracion', methods=['GET', 'POST'])
@login_requerido
@negocio_requerido
@rol_requerido(['encargado'])
def configuracion():
    bd = obtener_bd()
    cursor = bd.cursor()
    conn_sistema = sqlite3.connect(Config.BD_SISTEMA)
    c_sistema = conn_sistema.cursor()

    if request.method == 'POST':
        accion = request.form.get('accion', '')
        
        if accion == 'toggle_modo_prueba':
            nuevo = '1' if request.form.get('modo_prueba', '0') == '1' else '0'
            session['modo_prueba'] = (nuevo == '1')
            cursor.execute("INSERT OR REPLACE INTO configuraciones (clave, valor) VALUES ('modo_prueba', ?)", (nuevo,))
            bd.commit()
            flash(f'Modo {"Prueba" if nuevo=="1" else "Normal"} activado.', 'success')
            return redirect(url_for('configuracion.configuracion'))

        elif accion == 'editar_negocio':
            nombre = request.form.get('nombre', '').strip()
            telefono = request.form.get('telefono', '').strip()
            email = request.form.get('email_negocio', '').strip()
            descripcion = request.form.get('descripcion', '').strip()
            if nombre:
                c_sistema.execute("UPDATE negocios SET nombre=?, telefono=?, email=?, descripcion=? WHERE id=?",
                                  (nombre, telefono, email, descripcion, session['negocio_id']))
                conn_sistema.commit()
                session['negocio_nombre'] = nombre
                flash('Datos actualizados.', 'success')
            else:
                flash('El nombre es obligatorio.', 'danger')

        elif accion == 'crear_usuario':
            nombre = request.form.get('nombre', '').strip()
            rol = request.form.get('rol', '')
            password = request.form.get('password', '')
            if nombre and rol in ['vendedor', 'cliente', 'proveedor']:
                sufijo = random.randint(1000, 9999)
                email = f"{nombre.lower().replace(' ', '_')}_{sufijo}@{session.get('negocio_nombre', 'negocio')}.com"
                password_hash = '' if rol == 'cliente' else generate_password_hash(password)
                if not c_sistema.execute("SELECT id FROM usuarios WHERE email=?", (email,)).fetchone():
                    token_acceso = secrets.token_urlsafe(16)
                    c_sistema.execute("INSERT INTO usuarios (email, nombre, password, telefono, rol, activo, negocio_id, creado_por, access_token) VALUES (?,?,?,?,?,?,?,?,?)",
                                      (email, nombre, password_hash, '', rol, 1, session['negocio_id'], session['usuario_id'], token_acceso))
                    c_sistema.execute("INSERT OR IGNORE INTO permisos (usuario_id) VALUES (?)", (c_sistema.lastrowid,))
                    conn_sistema.commit()
                    link_acceso = url_for('auth.acceso_directo', token=token_acceso, _external=True)
                    flash(f'Usuario {nombre} creado como {rol}.', 'success')
                    flash(f'Link de acceso directo: {link_acceso}', 'info')
                else:
                    flash('Ya existe un usuario con ese correo.', 'danger')
            else:
                flash('Complete todos los campos.', 'danger')

        elif accion == 'cambiar_tema':
            tema = request.form.get('tema', 'claro')
            cursor.execute("INSERT OR REPLACE INTO configuraciones (clave, valor) VALUES ('tema', ?)", (tema,))
            bd.commit()
            session['tema'] = tema
            flash('Tema actualizado.', 'success')

        elif accion == 'agregar_tasa':
            fecha = request.form.get('fecha_tasa')
            try:
                tasa_val = float(request.form.get('tasa_valor', 0))
                if tasa_val > 0:
                    guardar_tasa(tasa_val, fecha)
                    flash('Tasa guardada correctamente.', 'success')
                else:
                    flash('La tasa debe ser mayor que 0.', 'danger')
            except:
                flash('Tasa inválida.', 'danger')

        elif accion == 'cambiar_password_negocio':
            nueva_password = generar_password()
            nuevo_hash = generate_password_hash(nueva_password)
            c_sistema.execute("UPDATE negocios SET password=? WHERE id=?", (nuevo_hash, session['negocio_id']))
            conn_sistema.commit()
            flash(f'🔑 Nueva contraseña del negocio: {nueva_password}', 'info')
            flash('⚠️ Cópiala ahora. No se volverá a mostrar.', 'warning')

        elif accion == 'guardar_permisos':
            try:
                usuario_id = int(request.form.get('usuario_id', 0))
                if usuario_id:
                    permisos = {k: request.form.get(k, '0') == '1' for k in ['ver_inventario', 'modificar_inventario',
                                'ver_contabilidad', 'modificar_contabilidad', 'ver_facturas', 'anular_facturas', 'gestionar_usuarios']}
                    c_sistema.execute("INSERT OR REPLACE INTO permisos (usuario_id, ver_inventario, modificar_inventario, ver_contabilidad, modificar_contabilidad, ver_facturas, anular_facturas, gestionar_usuarios) VALUES (?,?,?,?,?,?,?,?)",
                                      (usuario_id, *permisos.values()))
                    conn_sistema.commit()
                    flash('Permisos actualizados correctamente.', 'success')
            except:
                flash('Error al guardar permisos.', 'danger')

        elif accion == 'reset_password':
            try:
                usuario_id = int(request.form.get('usuario_id', 0))
                nueva = request.form.get('nueva', '')
                if usuario_id and nueva:
                    c_sistema.execute("UPDATE usuarios SET password=? WHERE id=? AND negocio_id=?",
                                      (generate_password_hash(nueva), usuario_id, session['negocio_id']))
                    conn_sistema.commit()
                    flash('Contraseña restablecida correctamente.', 'success')
                else:
                    flash('Debe ingresar una nueva contraseña.', 'danger')
            except:
                flash('Error al restablecer contraseña.', 'danger')

    # Obtener datos del negocio
    c_sistema.execute("SELECT nombre, telefono, email, descripcion FROM negocios WHERE id=?", (session['negocio_id'],))
    negocio = c_sistema.fetchone()
    datos_negocio = {'nombre': negocio[0] if negocio else '', 'telefono': negocio[1] if negocio else '',
                     'email_negocio': negocio[2] if negocio else '', 'descripcion': negocio[3] if negocio else ''}

    cursor.execute("SELECT valor FROM configuraciones WHERE clave='tema'")
    tema_actual = (cursor.fetchone() or ['claro'])[0]
    cursor.execute("SELECT valor FROM configuraciones WHERE clave='modo_prueba'")
    modo_prueba_actual = (cursor.fetchone() or ['0'])[0] == '1'

    c_sistema.execute("SELECT id, nombre, email, rol FROM usuarios WHERE negocio_id=? AND id != ?",
                      (session['negocio_id'], session['usuario_id']))
    usuarios = c_sistema.fetchall()

    permisos_usuarios = {}
    for u in usuarios:
        c_sistema.execute("SELECT * FROM permisos WHERE usuario_id=?", (u[0],))
        perm = c_sistema.fetchone()
        if perm:
            permisos_usuarios[u[0]] = {k: perm[k] for k in ['ver_inventario', 'modificar_inventario', 'ver_contabilidad',
                                       'modificar_contabilidad', 'ver_facturas', 'anular_facturas', 'gestionar_usuarios']}
        else:
            permisos_usuarios[u[0]] = dict.fromkeys(['ver_inventario', 'modificar_inventario', 'ver_contabilidad',
                                       'modificar_contabilidad', 'ver_facturas', 'anular_facturas', 'gestionar_usuarios'], 0)

    cursor.execute("SELECT fecha, tasa FROM tasas_historicas ORDER BY fecha DESC")
    tasas = cursor.fetchall()
    conn_sistema.close()

    return render_template('configuracion.html', 
                          tema_actual=tema_actual,
                          modo_prueba_actual=modo_prueba_actual,
                          usuarios=usuarios,
                          negocio=datos_negocio,
                          tasas=tasas,
                          permisos_usuarios=permisos_usuarios)

@configuracion_bp.route('/eliminar_usuario/<int:usuario_id>')
@login_requerido
@negocio_requerido
@rol_requerido(['encargado'])
def eliminar_usuario(usuario_id):
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT id, nombre, negocio_id FROM usuarios WHERE id=?", (usuario_id,))
        usuario = c.fetchone()
        if not usuario or usuario[2] != session['negocio_id']:
            flash('Usuario no encontrado.', 'danger')
        elif usuario[0] == session['usuario_id']:
            flash('No puedes eliminarte a ti mismo.', 'danger')
        else:
            c.execute("DELETE FROM permisos WHERE usuario_id=?", (usuario_id,))
            c.execute("DELETE FROM usuarios WHERE id=?", (usuario_id,))
            conn.commit()
            registrar_log("Eliminación de usuario", session['usuario_id'], f"Usuario {usuario[1]}")
            flash(f'Usuario {usuario[1]} eliminado.', 'success')
    return redirect(url_for('configuracion.configuracion'))
