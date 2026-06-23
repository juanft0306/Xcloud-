import string
import secrets
from werkzeug.security import generate_password_hash, check_password_hash

def generar_password(longitud=8):
    """Genera una contraseña aleatoria con letras y dígitos."""
    caracteres = string.ascii_letters + string.digits
    while True:
        pwd = ''.join(secrets.choice(caracteres) for _ in range(longitud))
        if any(c.isalpha() for c in pwd) and any(c.isdigit() for c in pwd):
            return pwd

# También podemos exponer las funciones de werkzeug directamente
# pero las dejamos así para que quede claro
