from flask import Blueprint, render_template, request, redirect, url_for, session, flash, send_file
from datetime import datetime, timedelta
from app.db.sqlite import obtener_bd
from app.utils.tasas import obtener_tasa
from app.utils.logs import registrar_log
from app.utils.decoradores import login_requerido, negocio_requerido, rol_requerido
import io
import csv

contabilidad_bp = Blueprint('contabilidad', __name__)

# ------------------------------------------------------------------
# FUNCIÓN PARA ASEGURAR TABLAS DE CONTABILIDAD
# ------------------------------------------------------------------
def _asegurar_tablas_contabilidad():
    bd = obtener_bd()
    cursor = bd.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS gastos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT,
        concepto TEXT NOT NULL, monto_usd REAL NOT NULL,
        categoria TEXT DEFAULT 'General', asiento_id INTEGER)''')
    bd.commit()

# ------------------------------------------------------------------
# CÁLCULO DE BALANCE
# ------------------------------------------------------------------
def calcular_balance():
    bd = obtener_bd()
    cursor = bd.cursor()
    caja = cursor.execute("SELECT SUM(debe) - SUM(haber) FROM movimientos WHERE cuenta LIKE 'Caja %'").fetchone()[0] or 0
    inventario = cursor.execute("SELECT SUM(costo_usd * stock) FROM productos").fetchone()[0] or 0
    cuentas_por_pagar = cursor.execute("SELECT SUM(debe) - SUM(haber) FROM movimientos WHERE cuenta='Cuentas por Pagar'").fetchone()[0] or 0
    activos = caja + inventario
    pasivos = cuentas_por_pagar
    patrimonio = activos - pasivos
    return {'caja': caja, 'inventario': inventario, 'activos_totales': activos,
            'cuentas_por_pagar': pasivos, 'pasivos_totales': pasivos, 'patrimonio': patrimonio}

# ------------------------------------------------------------------
# CÁLCULO DE RESULTADOS
# ------------------------------------------------------------------
def calcular_resultados(fecha_inicio=None, fecha_fin=None):
    bd = obtener_bd()
    cursor = bd.cursor()
    condicion = ""
    params = []
    if fecha_inicio and fecha_fin:
        condicion = " AND a.fecha BETWEEN ? AND ?"
        params = [fecha_inicio, fecha_fin]

    cursor.execute(f"SELECT COALESCE(SUM(m.haber),0) FROM movimientos m JOIN asientos a ON m.asiento_id = a.id WHERE m.cuenta='Ingresos por Ventas'{condicion}", params)
    ingresos = cursor.fetchone()[0]
    cursor.execute(f"SELECT COALESCE(SUM(m.debe),0) FROM movimientos m JOIN asientos a ON m.asiento_id = a.id WHERE m.cuenta='Costo de Ventas'{condicion}", params)
    costos = cursor.fetchone()[0]
    cursor.execute(f"SELECT COALESCE(SUM(m.debe),0) FROM movimientos m JOIN asientos a ON m.asiento_id = a.id WHERE m.cuenta='Comisión Sistema'{condicion}", params)
    comision = cursor.fetchone()[0]
    cursor.execute(f"SELECT COALESCE(SUM(m.debe),0) FROM movimientos m JOIN asientos a ON m.asiento_id = a.id WHERE m.cuenta='Gastos Operativos'{condicion}", params)
    gastos_operativos = cursor.fetchone()[0]

    utilidad_bruta = ingresos - costos
    utilidad_neta = utilidad_bruta - comision - gastos_operativos
    return {'ingresos': ingresos, 'costos': costos, 'utilidad_bruta': utilidad_bruta,
            'comision': comision, 'gastos_operativos': gastos_operativos, 'utilidad_neta': utilidad_neta}

# ------------------------------------------------------------------
# CONTABILIDAD PRINCIPAL
# ------------------------------------------------------------------
@contabilidad_bp.route('/contabilidad')
@login_requerido
@negocio_requerido
@rol_requerido(['encargado'])
def contabilidad():
    _asegurar_tablas_contabilidad()
    balance = calcular_balance()
    resultados = calcular_resultados()

    hoy = datetime.now()
    inicio_semana = (hoy - timedelta(days=hoy.weekday())).strftime('%Y-%m-%d')
    fin_semana = hoy.strftime('%Y-%m-%d')
    inicio_mes = hoy.replace(day=1).strftime('%Y-%m-%d')
    inicio_ano = hoy.replace(month=1, day=1).strftime('%Y-%m-%d')

    resultados_semana = calcular_resultados(inicio_semana, fin_semana)
    resultados_mes = calcular_resultados(inicio_mes, hoy.strftime('%Y-%m-%d'))
    resultados_ano = calcular_resultados(inicio_ano, hoy.strftime('%Y-%m-%d'))

    return render_template('contabilidad.html',
                           balance=balance, resultados=resultados,
                           resultados_semana=resultados_semana,
                           resultados_mes=resultados_mes,
                           resultados_ano=resultados_ano,
                           inicio_semana=inicio_semana,
                           inicio_mes=inicio_mes,
                           inicio_ano=inicio_ano,
                           modo_prueba=session.get('modo_prueba', False))

# ------------------------------------------------------------------
# LIBRO DIARIO
# ------------------------------------------------------------------
@contabilidad_bp.route('/libro_diario')
@login_requerido
@negocio_requerido
@rol_requerido(['encargado'])
def libro_diario():
    _asegurar_tablas_contabilidad()
    bd = obtener_bd()
    cursor = bd.cursor()
    pagina = request.args.get('pagina', 1, type=int)
    por_pagina = 20
    total = cursor.execute("SELECT COUNT(*) FROM asientos").fetchone()[0]
    asientos = cursor.execute("""SELECT a.id, a.fecha, a.concepto, a.numero_factura, a.tasa_usada,
                                        (SELECT GROUP_CONCAT(m.cuenta || ': ' || (m.debe - m.haber) || ' | ') FROM movimientos m WHERE m.asiento_id = a.id) as movimientos
                                 FROM asientos a ORDER BY a.fecha DESC, a.id DESC LIMIT ? OFFSET ?""",
                              (por_pagina, (pagina-1)*por_pagina)).fetchall()
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
    return render_template('libro_diario.html', asientos=asientos, pagina=pagina, total_paginas=total_paginas)

# ------------------------------------------------------------------
# GASTOS
# ------------------------------------------------------------------
@contabilidad_bp.route('/gastos', methods=['GET', 'POST'])
@login_requerido
@negocio_requerido
@rol_requerido(['encargado'])
def gastos():
    _asegurar_tablas_contabilidad()
    bd = obtener_bd()
    cursor = bd.cursor()

    if request.method == 'POST':
        concepto = request.form['concepto']
        monto = float(request.form['monto'])
        categoria = request.form.get('categoria', 'General')
        fecha = request.form.get('fecha', datetime.now().strftime('%Y-%m-%d'))
        if monto <= 0:
            flash("Monto debe ser positivo", "danger")
            return redirect(url_for('contabilidad.gastos'))

        bd.execute("BEGIN")
        try:
            cursor.execute("INSERT INTO asientos (fecha, concepto, referencia, usuario) VALUES (?,?,?,?)",
                           (fecha, f"Gasto: {concepto}", "GASTO", session.get('usuario_nombre')))
            asiento_id = cursor.lastrowid
            cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,?,0)",
                           (asiento_id, "Gastos Operativos", monto))
            cursor.execute("INSERT INTO movimientos (asiento_id, cuenta, debe, haber) VALUES (?,?,0,?)",
                           (asiento_id, "Caja", monto))
            cursor.execute("INSERT INTO gastos (fecha, concepto, monto_usd, categoria, asiento_id) VALUES (?,?,?,?,?)",
                           (fecha, concepto, monto, categoria, asiento_id))
            bd.commit()
            flash("Gasto registrado correctamente", "success")
        except Exception as e:
            bd.rollback()
            flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('contabilidad.contabilidad'))

    filtro_categoria = request.args.get('categoria', '')
    filtro_fecha = request.args.get('fecha', '')
    query = "SELECT fecha, concepto, monto_usd, categoria FROM gastos WHERE 1=1"
    params = []
    if filtro_categoria:
        query += " AND categoria = ?"
        params.append(filtro_categoria)
    if filtro_fecha:
        query += " AND fecha = ?"
        params.append(filtro_fecha)
    query += " ORDER BY fecha DESC LIMIT 30"
    gastos_lista = cursor.execute(query, params).fetchall()
    total_gastos = cursor.execute("SELECT COALESCE(SUM(monto_usd),0) FROM gastos").fetchone()[0]
    categorias = cursor.execute("SELECT DISTINCT categoria FROM gastos ORDER BY categoria").fetchall()

    return render_template('gastos.html',
                           gastos=gastos_lista,
                           total_gastos=total_gastos,
                           categorias=categorias,
                           filtro_categoria=filtro_categoria,
                           filtro_fecha=filtro_fecha)

# ------------------------------------------------------------------
# EXPORTAR A EXCEL (CSV)
# ------------------------------------------------------------------
@contabilidad_bp.route('/exportar_excel')
@login_requerido
@negocio_requerido
@rol_requerido(['encargado'])
def exportar_excel():
    _asegurar_tablas_contabilidad()
    bd = obtener_bd()
    cursor = bd.cursor()
    asientos = cursor.execute("""SELECT a.id, a.fecha, a.concepto, a.numero_factura, m.cuenta, m.debe, m.haber
                                 FROM asientos a JOIN movimientos m ON a.id = m.asiento_id ORDER BY a.fecha, a.id""").fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID Asiento', 'Fecha', 'Concepto', 'Factura', 'Cuenta', 'Debe', 'Haber'])
    for a in asientos:
        writer.writerow([a['id'], a['fecha'], a['concepto'], a['numero_factura'], a['cuenta'], a['debe'], a['haber']])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode('utf-8')), mimetype='text/csv',
                     as_attachment=True, download_name=f'contabilidad_{datetime.now().strftime("%Y%m%d")}.csv')
