"""GET /api/rrhh con objetivos cargados (S8).

Antes, el listado leía Goal.deadline, un campo que el modelo no tiene: con al menos un
objetivo respondía 500. Goal solo tiene 'period', así que 'deadline' se devuelve en null.
Datos sintéticos rotulados PROBE; SQLite en memoria.
"""

from models import Employee, Goal, db
from security import generate_access_token
from sesion_de_prueba import asegurar_usuario, marcar_sesion


def _con_un_objetivo(app):
    with app.app_context():
        empleado = Employee(first_name="PROBE", last_name="Empleado")
        db.session.add(empleado)
        db.session.flush()
        db.session.add(Goal(
            employee_id=empleado.id,
            description="PROBE objetivo",
            period="2026-Q4",
            target_value=10.0,
            current_value=4.0,
        ))
        db.session.commit()


def test_rrhh_con_objetivo_responde_200_con_sesion(app_seguridad):
    _con_un_objetivo(app_seguridad)
    uid = asegurar_usuario(app_seguridad, 2, "PROBE-hr", "hr")
    cliente = app_seguridad.test_client()
    marcar_sesion(cliente, uid)

    respuesta = cliente.get("/api/rrhh")

    assert respuesta.status_code == 200, respuesta.get_data(as_text=True)[:200]
    datos = respuesta.get_json()
    assert datos["employee_count"] == 1
    objetivo = datos["goals"][0]
    assert objetivo["description"] == "PROBE objetivo"
    assert objetivo["employee_name"] == "PROBE Empleado"
    assert objetivo["target_value"] == 10.0
    assert objetivo["current_value"] == 4.0
    assert objetivo["deadline"] is None


def test_rrhh_con_objetivo_responde_200_con_jwt(app_seguridad):
    _con_un_objetivo(app_seguridad)
    uid = asegurar_usuario(app_seguridad, 2, "PROBE-hr", "hr")
    with app_seguridad.app_context():
        token = generate_access_token(uid, "PROBE-hr", "hr")

    respuesta = app_seguridad.test_client().get(
        "/api/rrhh", headers={"Authorization": f"Bearer {token}"}
    )

    assert respuesta.status_code == 200, respuesta.get_data(as_text=True)[:200]
    assert respuesta.get_json()["goals"][0]["deadline"] is None
