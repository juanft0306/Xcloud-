# ------------------------------------------------------------------
# CAMBIAR CONTRASEÑA DE USUARIO
# ------------------------------------------------------------------
@auth_bp.route('/cambiar_password', methods=['GET', 'POST'])
@login_requerido
def cambiar_password():
    if request.method == 'POST':
        actual = request.form['actual']
        nueva = request.form['nueva']
        confirmacion = request.form['confirmacion']
        if nueva != confirmacion:
            flash('Las contraseñas no coinciden', 'danger')
            return redirect(url_for('auth.cambiar_password'))
        with sqlite3.connect(Config.BD_SISTEMA) as conn:
            c = conn.cursor()
            c.execute("SELECT password FROM usuarios WHERE id=?", (session['usuario_id'],))
            user = c.fetchone()
            if not user or not check_password_hash(user[0], actual):
                flash('Contraseña actual incorrecta', 'danger')
                return redirect(url_for('auth.cambiar_password'))
            c.execute("UPDATE usuarios SET password=? WHERE id=?", (generate_password_hash(nueva), session['usuario_id']))
            conn.commit()
        registrar_log("Cambio de contraseña", session['usuario_id'])
        flash('Contraseña actualizada', 'success')
        return redirect(url_for('dashboard.dashboard_negocio'))
    return render_template('cambiar_password.html')
