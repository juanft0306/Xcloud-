from flask import Blueprint, render_template, request, redirect, url_for, session, flash, send_file
from datetime import datetime
import io
import csv
import os
from app.db.sqlite import obtener_bd
from app.utils.decoradores import login_requerido, negocio_requerido, rol_requerido
from app.config import Config

reportes_bp = Blueprint('reportes', __name__)

# ------------------------------------------------------------------
# PÁGINA PRINCIPAL DE REPORTES
# ------------------------------------------------------------------
@reportes_bp.route('/reportes')
@login_requerido
@negocio_requerido
@rol_requerido(['encargado'])
def reportes():
    return render_template('reportes.html')

# ------------------------------------------------------------------
# EXPORTAR A CSV (productos o facturas)
# ------------------------------------------------------------------
@reportes_bp.route('/exportar_csv')
@login_requerido
@negocio_requerido
@rol_requerido(['encargado'])
def exportar_csv():
    tipo = request.args.get('tipo', 'productos')
    bd = obtener_bd()
    cursor = bd.cursor()
    
    if tipo == 'productos':
        datos = cursor.execute("SELECT sku, descripcion, costo_usd, stock FROM productos").fetchall()
        encabezados = ['SKU', 'Descripción', 'Costo USD', 'Stock']
        nombre_archivo = f'productos_{datetime.now().strftime("%Y%m%d")}.csv'
    elif tipo == 'facturas':
        datos = cursor.execute("SELECT numero, fecha, cliente, total_usd, metodo_pago FROM facturas ORDER BY fecha DESC").fetchall()
        encabezados = ['Número', 'Fecha', 'Cliente', 'Total USD', 'Método']
        nombre_archivo = f'facturas_{datetime.now().strftime("%Y%m%d")}.csv'
    else:
        flash('Tipo de exportación no válido.', 'danger')
        return redirect(url_for('reportes.reportes'))
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(encabezados)
    for fila in datos:
        writer.writerow([str(x) for x in fila])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=nombre_archivo
    )

# ------------------------------------------------------------------
# DESCARGAR BASE DE DATOS COMPLETA
# ------------------------------------------------------------------
@reportes_bp.route('/descargar_bd')
@login_requerido
@negocio_requerido
@rol_requerido(['encargado'])
def descargar_bd():
    # No permitir en modo verificación
    if session.get('negocio_id') == 'verificacion':
        flash('No disponible en modo verificación', 'danger')
        return redirect(url_for('dashboard.dashboard_negocio'))
    
    ruta = Config.BD_NOMBRE_BASE.format(session['negocio_id'])
    if not os.path.exists(ruta):
        flash('Base de datos no encontrada.', 'danger')
        return redirect(url_for('dashboard.dashboard_negocio'))
    
    return send_file(
        ruta,
        as_attachment=True,
        download_name=f'negocio_{session["negocio_id"]}_{datetime.now().strftime("%Y%m%d")}.db'
    )

# ------------------------------------------------------------------
# GENERAR FACTURA EN PDF
# ------------------------------------------------------------------
@reportes_bp.route('/factura_pdf/<int:num>')
@login_requerido
@negocio_requerido
def factura_pdf(num):
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
    except ImportError:
        flash('Requiere reportlab: pip install reportlab', 'danger')
        return redirect(url_for('ventas.listar_facturas'))
    
    bd = obtener_bd()
    cursor = bd.cursor()
    factura = cursor.execute("SELECT * FROM facturas WHERE numero=?", (num,)).fetchone()
    if not factura:
        flash("Factura no encontrada", "danger")
        return redirect(url_for('ventas.listar_facturas'))
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elementos = []
    styles = getSampleStyleSheet()
    
    # Datos del negocio
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT nombre, telefono, email FROM negocios WHERE id=?", (session['negocio_id'],))
        neg = c.fetchone()
    
    # Encabezado
    elementos.append(Paragraph(f"<b>{neg[0] if neg else 'Negocio'}</b>", styles['Heading2']))
    if neg and neg[1]:
        elementos.append(Paragraph(f"Tel: {neg[1]}", styles['Normal']))
    if neg and neg[2]:
        elementos.append(Paragraph(f"Email: {neg[2]}", styles['Normal']))
    elementos.append(Spacer(1, 12))
    
    # Datos de la factura
    elementos.append(Paragraph(f"<b>Factura Nº:</b> {factura['numero']}", styles['Normal']))
    elementos.append(Paragraph(f"<b>Fecha:</b> {factura['fecha']}", styles['Normal']))
    elementos.append(Paragraph(f"<b>Cliente:</b> {factura['cliente']}", styles['Normal']))
    elementos.append(Paragraph(f"<b>Método de pago:</b> {factura['metodo_pago']}", styles['Normal']))
    elementos.append(Spacer(1, 12))
    
    # Detalle de productos
    detalles = cursor.execute("SELECT sku, cantidad, precio_unitario_usd FROM venta_detalle WHERE factura_numero=?", (num,)).fetchall()
    data = [['Producto', 'Cantidad', 'Precio USD', 'Subtotal']]
    for d in detalles:
        subtotal = d['cantidad'] * d['precio_unitario_usd']
        data.append([d['sku'], str(d['cantidad']), f"${d['precio_unitario_usd']:.2f}", f"${subtotal:.2f}"])
    data.append(['', '', 'Total USD', f"${factura['total_usd']:.2f}"])
    
    tabla = Table(data)
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
    ]))
    elementos.append(tabla)
    
    # Pie de página
    elementos.append(Spacer(1, 12))
    elementos.append(Paragraph("Gracias por su compra.", styles['Normal']))
    
    doc.build(elementos)
    buffer.seek(0)
    
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'factura_{num}_{datetime.now().strftime("%Y%m%d")}.pdf'
  )
