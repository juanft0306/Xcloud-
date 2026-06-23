import os
from flask import Flask, g
from datetime import datetime
from app.config import Config
from app.db.sqlite import inicializar_sistema, obtener_bd, cerrar_bd

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Inicializar sistema (crea tablas si no existen)
    inicializar_sistema()

    # Contexto para templates
    @app.context_processor
    def inject_now():
        return {'now': datetime.now}

    # Teardown: cerrar conexión a BD al final de cada petición
    @app.teardown_appcontext
    def teardown_db(error):
        cerrar_bd(error)

    # --- Registro de Blueprints (rutas) ---
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.inventario import inventario_bp
    from app.routes.ventas import ventas_bp
    from app.routes.contabilidad import contabilidad_bp
    from app.routes.configuration import configuration_bp
    from app.routes.programador import programador_bp
    from app.routes.tienda import tienda_bp
    from app.routes.proveedor import proveedor_bp
    from app.routes.api import api_bp
    from app.routes.reportes import reportes_bp
    from app.routes.soporte import soporte_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(inventario_bp)
    app.register_blueprint(ventas_bp)
    app.register_blueprint(contabilidad_bp)
    app.register_blueprint(configuracion_bp)
    app.register_blueprint(programador_bp)
    app.register_blueprint(tienda_bp)
    app.register_blueprint(proveedor_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(reportes_bp)
    app.register_blueprint(soporte_bp)

    return app
