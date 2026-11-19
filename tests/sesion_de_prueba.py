"""Usuarios y sesiones web sintéticos para la suite (datos rotulados PROBE).

Desde la revalidación por request, una sesión de prueba necesita un usuario activo en
la base y su huella. Este módulo la arma con datos_de_sesion_web, la misma función que
usa el login, así que pasa la revalidación igual que una sesión real. Nunca apunta a
una base que no sea la de la prueba.
"""

from models import db
from models.core.user import User
from security import datos_de_sesion_web

ADMIN_PRUEBA_ID = 1
CLAVE_PRUEBA = "PROBE-clave-no-real"


def asegurar_usuario(app, usuario_id, username, role):
    """Crea el usuario sintético si no existe y le fija clave de prueba. Devuelve su id."""
    with app.app_context():
        usuario = db.session.get(User, usuario_id)
        if usuario is None:
            usuario = User(id=usuario_id, username=username, role=role, active=True)
            db.session.add(usuario)
        if usuario.password_hash is None:
            usuario.set_password(CLAVE_PRUEBA)
        db.session.commit()
        return usuario.id


def marcar_sesion(cliente, usuario_id):
    """Deja la sesión del cliente con la identidad y la huella del usuario indicado."""
    with cliente.application.app_context():
        usuario = db.session.get(User, usuario_id)
        if usuario.password_hash is None:
            usuario.set_password(CLAVE_PRUEBA)
            db.session.commit()
        datos = datos_de_sesion_web(usuario)
    with cliente.session_transaction() as sesion:
        sesion.update(datos)


def cambiar_usuario(cliente, usuario_id, **campos):
    """Cambia campos del usuario en la base (username, role, active...) y remarca la sesión.

    Usar esto en lugar de tocar session["role"]: la revalidación toma el rol de la base.
    """
    with cliente.application.app_context():
        usuario = db.session.get(User, usuario_id)
        for campo, valor in campos.items():
            setattr(usuario, campo, valor)
        db.session.commit()
    marcar_sesion(cliente, usuario_id)
