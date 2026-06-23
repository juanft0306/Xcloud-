import os
import sqlite3
from datetime import datetime
from flask import g, current_app
from werkzeug.security import generate_password_hash
from app.config import Config

# ------------------------------------------------------------------
# BLOQUE 2 - INICIALIZAR SISTEMA
# ------------------------------------------------------------------
def inicializar_sistema():
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL, password TEXT NOT NULL, telefono TEXT,
            rol TEXT DEFAULT 'cliente', activo INTEGER DEFAULT 0,
            negocio_id INTEGER, creado_por INTEGER, access_token TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS negocios (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL, telefono TEXT, descripcion TEXT,
            programador_id INTEGER, encargado_id INTEGER, fecha_creacion TEXT,
            estado TEXT DEFAULT 'pendiente', password TEXT,
            tiene_clientes INTEGER DEFAULT 1, licencia_activa INTEGER DEFAULT 1)''')
        c.execute('''CREATE TABLE IF NOT EXISTS solicitudes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nombre_negocio TEXT,
            email TEXT, telefono TEXT, descripcion TEXT, password TEXT,
            fecha_solicitud TEXT, estado TEXT DEFAULT 'pendiente',
            encargado_email TEXT, encargado_password TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER,
            negocio_id INTEGER, fecha_pedido TEXT, total_usd REAL,
            metodo_pago TEXT, estado TEXT DEFAULT 'pendiente',
            proveedor_id INTEGER, pago_verificado INTEGER DEFAULT 0,
            pago_verificado_por TEXT, codigo_verificacion TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS detalle_pedido (
            id INTEGER PRIMARY KEY AUTOINCREMENT, pedido_id INTEGER,
            sku TEXT, cantidad INTEGER, precio_unitario_usd REAL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL,
            usuario_id INTEGER, accion TEXT NOT NULL, detalles TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS intentos_login (
            id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL,
            fecha TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS notificaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER,
            mensaje TEXT NOT NULL, leida INTEGER DEFAULT 0, fecha TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS permisos (
            usuario_id INTEGER PRIMARY KEY,
            ver_inventario INTEGER DEFAULT 0, modificar_inventario INTEGER DEFAULT 0,
            ver_contabilidad INTEGER DEFAULT 0, modificar_contabilidad INTEGER DEFAULT 0,
            ver_facturas INTEGER DEFAULT 0, anular_facturas INTEGER DEFAULT 0,
            gestionar_usuarios INTEGER DEFAULT 0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, negocio_id INTEGER,
            usuario_id INTEGER, asunto TEXT NOT NULL, mensaje TEXT NOT NULL,
            respuesta TEXT, estado TEXT DEFAULT 'abierto', fecha TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS config_global (
            clave TEXT PRIMARY KEY, valor TEXT)''')
        c.execute("INSERT OR IGNORE INTO config_global (clave, valor) VALUES ('comision', '0')")
        c.execute('''CREATE TABLE IF NOT EXISTS suscripciones (
            negocio_id INTEGER PRIMARY KEY, tarifa_mensual REAL DEFAULT 5.0,
            fecha_proximo_pago TEXT, activa INTEGER DEFAULT 0,
            periodicidad TEXT DEFAULT 'mensual', metodo_cobro TEXT DEFAULT 'transferencia',
            moneda TEXT DEFAULT 'USD', monto_cobro REAL DEFAULT 5.0,
            tasa_personalizada REAL DEFAULT 0.0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS config_cobros (
            clave TEXT PRIMARY KEY, valor TEXT)''')
        c.execute("INSERT OR IGNORE INTO config_cobros (clave, valor) VALUES ('tasa_cobro', '0')")
        c.execute("INSERT OR IGNORE INTO config_cobros (clave, valor) VALUES ('pasarela_activa', 'transferencia')")

        # Usuario programador por defecto
        if not c.execute("SELECT id FROM usuarios WHERE email='programador@sys.com'").fetchone():
            c.execute("INSERT INTO usuarios (email, nombre, password, rol, activo) VALUES (?,?,?,?,?)",
                      ('programador@sys.com', 'Programador', generate_password_hash('prog123'), 'programador', 1))
        if not c.execute("SELECT id FROM negocios WHERE email='programador@empresa.com'").fetchone():
            c.execute("INSERT INTO negocios (id, nombre, email, telefono, descripcion, programador_id, encargado_id, fecha_creacion, estado, password, tiene_clientes, licencia_activa) VALUES (1,?,?,?,?,?,?,?,?,?,?,?)",
                      ('Negocio del Programador', 'programador@empresa.com', '0000000000',
                       'Negocio propio del programador', 1, 1,
                       datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'aprobado',
                       generate_password_hash('prog123'), 1, 1))
        c.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_negocio ON usuarios(negocio_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_logs_fecha ON logs(fecha)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_notificaciones_usuario ON notificaciones(usuario_id, leida)")
        conn.commit()

    if not os.path.exists(Config.BD_NOMBRE_BASE.format(1)):
        crear_base_negocio(Config.BD_NOMBRE_BASE.format(1))

# ------------------------------------------------------------------
# BLOQUE 3 - CREAR BASE DE NEGOCIO
# ------------------------------------------------------------------
def crear_base_negocio(ruta_bd):
    with sqlite3.connect(ruta_bd) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS productos (
            sku TEXT PRIMARY KEY, descripcion TEXT NOT NULL, costo_usd REAL,
            stock INTEGER, limite_critico INTEGER DEFAULT 0, imagen_url TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS asientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, concepto TEXT,
            referencia TEXT, usuario TEXT, numero_factura TEXT, tasa_usada REAL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, asiento_id INTEGER,
            cuenta TEXT, debe REAL, haber REAL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS facturas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, numero TEXT UNIQUE,
            fecha TEXT, cliente TEXT, total_usd REAL, metodo_pago TEXT,
            asiento_id INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS venta_detalle (
            id INTEGER PRIMARY KEY AUTOINCREMENT, factura_numero TEXT,
            sku TEXT, cantidad INTEGER, precio_unitario_usd REAL)''')
        c.execute('CREATE TABLE IF NOT EXISTS config (clave TEXT PRIMARY KEY, valor TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS tasas_historicas (fecha TEXT PRIMARY KEY, tasa REAL)')
        c.execute("INSERT OR IGNORE INTO config (clave, valor) VALUES ('tasa', ?)", (str(Config.TASA_POR_DEFECTO),))
        c.execute('CREATE TABLE IF NOT EXISTS configuraciones (clave TEXT PRIMARY KEY, valor TEXT)')
        c.execute("INSERT OR IGNORE INTO configuraciones (clave, valor) VALUES ('tipo_factura', 'moderna')")
        c.execute("INSERT OR IGNORE INTO configuraciones (clave, valor) VALUES ('prefijo_factura', 'FAC-')")
        c.execute("INSERT OR IGNORE INTO configuraciones (clave, valor) VALUES ('reinicio_anual', '1')")
        c.execute('''CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT,
            concepto TEXT NOT NULL, monto_usd REAL NOT NULL,
            categoria TEXT DEFAULT 'General', asiento_id INTEGER)''')
        c.execute("CREATE INDEX IF NOT EXISTS idx_productos_stock ON productos(stock)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_asientos_fecha ON asientos(fecha)")
        conn.commit()

def migrar_negocio(ruta_bd):
    if not os.path.exists(ruta_bd): return
    with sqlite3.connect(ruta_bd) as conn:
        c = conn.cursor()
        try: c.execute("ALTER TABLE productos ADD COLUMN imagen_url TEXT")
        except sqlite3.OperationalError: pass
        try:
            c.execute('CREATE TABLE IF NOT EXISTS configuraciones (clave TEXT PRIMARY KEY, valor TEXT)')
            c.execute("INSERT OR IGNORE INTO configuraciones (clave, valor) VALUES ('tipo_factura', 'moderna')")
            c.execute("INSERT OR IGNORE INTO configuraciones (clave, valor) VALUES ('prefijo_factura', 'FAC-')")
            c.execute("INSERT OR IGNORE INTO configuraciones (clave, valor) VALUES ('reinicio_anual', '1')")
        except sqlite3.OperationalError: pass
        try:
            c.execute('''CREATE TABLE IF NOT EXISTS gastos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT,
                concepto TEXT NOT NULL, monto_usd REAL NOT NULL,
                categoria TEXT DEFAULT 'General', asiento_id INTEGER)''')
        except sqlite3.OperationalError: pass
        conn.commit()

# ------------------------------------------------------------------
# BLOQUE 4 - CONEXIÓN BD, TASAS, COMISIÓN (solo la función obtener_bd y cerrar_bd)
# ------------------------------------------------------------------
def obtener_bd():
    """Devuelve la conexión a la BD del negocio actual o a la de verificación."""
    from flask import session, g
    negocio_id = session.get('negocio_id')
    if negocio_id == 'verificacion':
        ruta = Config.BD_VERIFICACION
        if not os.path.exists(ruta):
            crear_base_negocio(ruta)
        migrar_negocio(ruta)
        if 'bd' not in g:
            g.bd = sqlite3.connect(ruta)
            g.bd.row_factory = sqlite3.Row
        return g.bd
    if not negocio_id or not str(negocio_id).isdigit():
        raise Exception("ID de negocio inválido")
    ruta = Config.BD_NOMBRE_BASE.format(int(negocio_id))
    if not os.path.exists(ruta):
        crear_base_negocio(ruta)
    migrar_negocio(ruta)
    if 'bd' not in g:
        g.bd = sqlite3.connect(ruta)
        g.bd.row_factory = sqlite3.Row
    return g.bd

def cerrar_bd(error):
    bd = g.pop('bd', None)
    if bd is not None:
        bd.close()
