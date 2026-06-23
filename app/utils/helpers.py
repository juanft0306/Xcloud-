import re
from app.db.sqlite import obtener_bd

def generar_sku_sugerido():
    bd = obtener_bd()
    cursor = bd.cursor()
    existentes = cursor.execute("SELECT sku FROM productos").fetchall()
    skus_set = {f['sku'] for f in existentes}
    for letra in [chr(i) for i in range(ord('A'), ord('Z')+1)]:
        for num in range(1, 1000):
            sku = f"{letra}{num:03d}"
            if sku not in skus_set:
                return sku
    return None

def normalizar(texto):
    texto = texto.lower().strip()
    for orig, dest in {'á':'a','é':'e','í':'i','ó':'o','ú':'u','ü':'u','ñ':'ny'}.items():
        texto = texto.replace(orig, dest)
    return texto

def extraer_entidades(texto):
    entidades = {}
    match = re.search(r'\b([a-zA-Z]\d{3})\b', texto)
    if match:
        entidades['sku'] = match.group(1).upper()
    nums = re.findall(r'\b(\d+)\b', texto)
    if nums:
        entidades['cantidad'] = int(nums[0])
    precios = re.findall(r'\b(\d+\.?\d*)\s*(dolares?|bs|bolivares?)?\b', texto)
    if precios:
        entidades['precio'] = float(precios[0][0])
    if any(p in texto for p in ['efectivo','cash']):
        entidades['metodo'] = 'Efectivo USD'
    elif any(p in texto for p in ['pago movil','pago móvil','movil']):
        entidades['metodo'] = 'Pago Móvil'
    elif any(p in texto for p in ['transferencia','transfer']):
        entidades['metodo'] = 'Transferencia'
    cliente_match = re.search(r'(?:para|cliente|a nombre de)\s+([a-zA-Záéíóúñ ]+)', texto)
    if cliente_match:
        entidades['cliente'] = cliente_match.group(1).strip().title()
    gasto_match = re.search(r'(?:gasto|pago|factura de)\s+([a-zA-Záéíóúñ ]+)', texto)
    if gasto_match:
        entidades['concepto'] = gasto_match.group(1).strip().title()
    prod_match = re.search(r'(?:producto|articulo|item)\s+([a-zA-Záéíóúñ ]+?)(?:\s+(?:cuesta|precio|stock|cantidad|$))', texto)
    if prod_match:
        entidades['nombre_producto'] = prod_match.group(1).strip().title()
    return entidades

def detectar_intencion(texto):
    texto_norm = normalizar(texto)
    if any(p in texto_norm for p in ['vender','vende','vendeme','registra venta','cobra','factura']):
        return 'venta'
    if any(p in texto_norm for p in ['cuanto stock','cuantas unidades','hay de','stock de','inventario de','consulta producto']):
        return 'consulta_stock'
    if any(p in texto_norm for p in ['agrega producto','nuevo producto','dar de alta','crea producto','añade producto']):
        return 'agregar_producto'
    if any(p in texto_norm for p in ['cuanto hay en caja','saldo de caja','caja','balance','cuanto dinero']):
        return 'caja'
    if any(p in texto_norm for p in ['gasto','registra gasto','pago de','factura de']):
        return 'gasto'
    if any(p in texto_norm for p in ['tasas','tasa','cambio','bcv','dolar','divisa']):
        return 'tasa'
    if any(p in texto_norm for p in ['ayuda','help','como se','explica','dime','que es','para que sirve','hola','buenos dias','buenas tardes']):
        return 'ayuda'
    return 'desconocido'
