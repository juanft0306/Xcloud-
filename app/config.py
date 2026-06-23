import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-cambiar-en-produccion'
    UPLOAD_FOLDER = 'app/static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    BD_SISTEMA = 'sistema.db'
    BD_NOMBRE_BASE = 'negocio_{}.db'
    BD_VERIFICACION = 'verificacion.db'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    TASA_POR_DEFECTO = 0.0
