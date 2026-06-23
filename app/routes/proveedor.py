from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.utils.decoradores import login_requerido, negocio_requerido, rol_requerido
from app.config import Config
import sqlite3

proveedor_bp = Blueprint('proveedor', __name__)

# ------------------------------------------------------------------
# PEDIDOS PARA PROVEEDOR
# ------------------------------------------------------------------
@proveedor_bp.route('/pedidos_proveedor')
@login_requerido
@negocio_requerido
@rol_requerido(['proveedor'])
def pedidos_proveedor():
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute('''SELECT p.id, p.fecha_pedido, p.total_usd, p.estado, u.nombre, p.metodo_pago, p.codigo_verificacion
                     FROM pedidos p JOIN usuarios u ON p.cliente_id = u.id
                     WHERE p.negocio_id=? AND p.estado NOT IN ('entregado','rechazado') ORDER BY p.fecha_pedido DESC''',
                  (session['negocio_id'],))
        pedidos = c.fetchall()
    return render_template('pedidos_proveedor.html', pedidos=pedidos)

# ------------------------------------------------------------------
# VERIFICAR ENTREGA CON CÓDIGO
# ------------------------------------------------------------------
@proveedor_bp.route('/proveedor/pedido/<int:pedido_id>/verificar_entrega', methods=['POST'])
@login_requerido
@rol_requerido(['proveedor'])
def verificar_entrega(pedido_id):
    codigo_ingresado = request.form.get('codigo', '').strip().upper()
    if not codigo_ingresado:
        flash('Debe ingresar un código.', 'danger')
        return redirect(url_for('proveedor.pedidos_proveedor'))
    
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT codigo_verificacion, estado FROM pedidos WHERE id=?", (pedido_id,))
        pedido = c.fetchone()
        if not pedido:
            flash('Pedido no encontrado.', 'danger')
            return redirect(url_for('proveedor.pedidos_proveedor'))
        if pedido['estado'] == 'entregado':
            flash('Ya fue entregado.', 'info')
            return redirect(url_for('proveedor.pedidos_proveedor'))
        if pedido['codigo_verificacion'] != codigo_ingresado:
            flash('Código incorrecto.', 'danger')
            return redirect(url_for('proveedor.pedidos_proveedor'))
        c.execute("UPDATE pedidos SET estado='entregado', pago_verificado=1, pago_verificado_por=? WHERE id=?",
                  (session['usuario_nombre'], pedido_id))
        conn.commit()
        flash('Entrega verificada. Pedido completado.', 'success')
        return redirect(url_for('proveedor.pedidos_proveedor'))

# ------------------------------------------------------------------
# RECHAZAR PEDIDO
# ------------------------------------------------------------------
@proveedor_bp.route('/proveedor/pedido/<int:pedido_id>/rechazar')
@login_requerido
@rol_requerido(['proveedor'])
def rechazar_pedido(pedido_id):
    with sqlite3.connect(Config.BD_SISTEMA) as conn:
        c = conn.cursor()
        c.execute("SELECT estado FROM pedidos WHERE id=?", (pedido_id,))
        pedido = c.fetchone()
        if not pedido:
            flash('Pedido no encontrado.', 'danger')
            return redirect(url_for('proveedor.pedidos_proveedor'))
        if pedido['estado'] == 'entregado':
            flash('Ya fue entregado, no se puede rechazar.', 'warning')
            return redirect(url_for('proveedor.pedidos_proveedor'))
        c.execute("UPDATE pedidos SET estado='rechazado', proveedor_id=? WHERE id=?",
                  (session['usuario_id'], pedido_id))
        conn.commit()
        flash('Pedido rechazado.', 'success')
        return redirect(url_for('proveedor.pedidos_proveedor'))
