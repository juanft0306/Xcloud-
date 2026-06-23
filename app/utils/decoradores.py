from functools import wraps
from flask import session, flash, redirect, url_for
import sqlite3
from app.config import Config

def obtener_rol_real():
    if 'usuario_id' not in session:
        return None
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT rol FROM usuarios WHERE id=?", (session['usuario_id'],))
        r = c.fetchone()
        return r[0] if r else None

def login_requerido(f):
    @wraps(f)
    def dec(*args, **kwargs):
        if 'usuario_id' not in session:
            flash('Inicia sesión', 'warning')
            return redirect(url_for('auth.portal'))
        return f(*args, **kwargs)
    return dec

def negocio_requerido(f):
    @wraps(f)
    def dec(*args, **kwargs):
        if 'negocio_id' not in session:
            flash('Selecciona un negocio', 'warning')
            return redirect(url_for('dashboard.seleccionar_negocio'))
        return f(*args, **kwargs)
    return dec

def rol_requerido(roles_permitidos):
    def decorador(f):
        @wraps(f)
        def env(*args, **kwargs):
            if 'usuario_id' not in session:
                flash('Inicia sesión', 'warning')
                return redirect(url_for('auth.portal'))
            rol_real = obtener_rol_real()
            if not rol_real:
                flash('Usuario no encontrado', 'danger')
                return redirect(url_for('auth.portal'))
            rol_activo = session.get('rol_activo')
            if not rol_activo:
                flash('Selecciona un rol', 'warning')
                return redirect(url_for('dashboard.dashboard_negocio'))
            jerarquia = {
                'programador': ['encargado', 'vendedor', 'cliente', 'proveedor'],
                'encargado': ['encargado', 'vendedor', 'cliente', 'proveedor'],
                'vendedor': ['vendedor'],
                'cliente': ['cliente'],
                'proveedor': ['proveedor']
            }
            if rol_activo not in jerarquia.get(rol_real, []):
                flash('Rol no autorizado', 'danger')
                return redirect(url_for('dashboard.dashboard_negocio'))
            if rol_activo not in roles_permitidos:
                flash('Acceso denegado', 'danger')
                return redirect(url_for('dashboard.dashboard_negocio'))
            return f(*args, **kwargs)
        return env
    return decorador

def permiso_requerido(permiso):
    def decorador(f):
        @wraps(f)
        def env(*args, **kwargs):
            with sqlite3.connect(Config.BD_SISTEMA) as conn:
                c = conn.cursor()
                c.execute(f"SELECT {permiso} FROM permisos WHERE usuario_id=?",
                          (session['usuario_id'],))
                r = c.fetchone()
                if not r or not r[0]:
                    flash('No tienes permiso para esta acción', 'danger')
                    return redirect(url_for('dashboard.dashboard_negocio'))
            return f(*args, **kwargs)
        return env
    return decorador
