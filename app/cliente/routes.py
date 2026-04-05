
from flask import Blueprint, flash, redirect, render_template, session, request, url_for
from model import Cliente, Usuario, db
from forms import ClienteForm 

clientesBp = Blueprint("clientes", __name__)

@clientesBp.route("/mi-perfil", methods=["GET"])
def detalle_cliente():
    
    usuario_id = session.get("usuarioId")  

    if not usuario_id:
        flash("Debes iniciar sesión para ver tu perfil.", "danger")
        return redirect(url_for("auth.iniciarSesion"))

    usuario = Usuario.query.get(usuario_id)

    if not usuario or not usuario.cliente:
        flash("No se pudo encontrar tu perfil.", "danger")
        return redirect(url_for("auth.iniciarSesion"))

    cliente = usuario.cliente

    return render_template(
        "cliente/detalle_cliente.html",
        cliente=cliente,
        usuario=usuario
    )
    
@clientesBp.route("/editar-perfil", methods=["GET", "POST"])
def editar_cliente():
   
    usuario_id = session.get("usuarioId")
    if not usuario_id:
        flash("Debes iniciar sesión para editar tu perfil.", "danger")
        return redirect(url_for("auth.iniciarSesion"))

    usuario = Usuario.query.get(usuario_id)
    if not usuario or not usuario.cliente:
        flash("No se encontró tu perfil.", "danger")
        return redirect(url_for("auth.iniciarSesion"))

    cliente = usuario.cliente

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        apellidoPaterno = request.form.get("apellidoPaterno", "").strip()
        apellidoMaterno = request.form.get("apellidoMaterno", "").strip()
        telefono = request.form.get("telefono", "").strip()
        alias = request.form.get("alias", "").strip()

        if not nombre or not apellidoPaterno:
            flash("Nombre y apellido paterno son obligatorios.", "danger")
            return redirect(url_for("clientes.cliente"))

        cliente.nombre = nombre
        cliente.apellidoPaterno = apellidoPaterno
        cliente.apellidoMaterno = apellidoMaterno if apellidoMaterno else None
        cliente.telefono = telefono if telefono else None
        cliente.alias = alias if alias else None

        db.session.commit()
        flash("Perfil actualizado correctamente.", "success")
        return redirect(url_for("clientes.detalle_cliente"))
    
    return render_template("cliente/editar_cliente.html", cliente=cliente, usuario=usuario)


@clientesBp.route("/desactivar-cuenta", methods=["POST"])
def desactivar_cliente():
  
    usuario_id = session.get("usuarioId")
    if not usuario_id:
        flash("Debes iniciar sesión para desactivar tu cuenta.", "danger")
        return redirect(url_for("auth.iniciarSesion"))

    usuario = Usuario.query.get(usuario_id)
    if not usuario or not usuario.cliente:
        flash("No se encontró tu perfil.", "danger")
        return redirect(url_for("auth.iniciarSesion"))

    cliente = usuario.cliente

    cliente.estado = False
    usuario.estado = "Inactivo"

    db.session.commit()
    session.clear()

    flash("Tu cuenta ha sido desactivada correctamente.", "success")
    return redirect(url_for("auth.iniciarSesion"))