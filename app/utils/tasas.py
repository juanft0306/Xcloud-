from datetime import datetime
from app.db.sqlite import obtener_bd

def obtener_tasa():
    """Devuelve la tasa del día actual."""
    bd = obtener_bd()
    c = bd.cursor()
    hoy = datetime.now().strftime('%Y-%m-%d')
    c.execute("SELECT tasa FROM tasas_historicas WHERE fecha = ?", (hoy,))
    f = c.fetchone()
    return f['tasa'] if f and f['tasa'] else 0.0

def obtener_tasa_por_fecha(fecha):
    bd = obtener_bd()
    c = bd.cursor()
    c.execute("SELECT tasa FROM tasas_historicas WHERE fecha = ?", (fecha,))
    f = c.fetchone()
    return f['tasa'] if f and f['tasa'] else 0.0

def guardar_tasa(tasa, fecha=None):
    bd = obtener_bd()
    with bd:
        bd.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES ('tasa', ?)", (str(tasa),))
        if fecha:
            bd.execute("INSERT OR REPLACE INTO tasas_historicas (fecha, tasa) VALUES (?, ?)", (fecha, tasa))

def obtener_comision():
    import sqlite3
    from app.config import Config
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT valor FROM config_global WHERE clave='comision'")
        f = c.fetchone()
        if f and f[0]:
            try:
                return max(0.0, min(5.0, float(f[0])))
            except:
                return 0.0
        return 0.0
