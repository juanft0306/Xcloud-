import sqlite3
from datetime import datetime, timedelta
from flask import session
from app.config import Config

def registrar_log(accion, usuario_id=None, detalles=""):
    try:
        with sqlite3.connect(Config.BD_SISTEMA) as conn:
            conn.execute("INSERT INTO logs (fecha, usuario_id, accion, detalles) VALUES (?,?,?,?)",
                         (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                          usuario_id or session.get('usuario_id'), accion, detalles))
    except:
        pass

def crear_notificacion(usuario_id, mensaje):
    try:
        with sqlite3.connect(Config.BD_SISTEMA) as conn:
            conn.execute("INSERT INTO notificaciones (usuario_id, mensaje, fecha) VALUES (?,?,?)",
                         (usuario_id, mensaje, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    except:
        pass

def intentos_fallidos(email):
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        limite = (datetime.now() - timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S')
        c.execute("SELECT COUNT(*) FROM intentos_login WHERE email=? AND fecha > ?", (email, limite))
        return c.fetchone()[0]

def registrar_intento_fallido(email):
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        conn.execute("INSERT INTO intentos_login (email, fecha) VALUES (?,?)",
                     (email, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
