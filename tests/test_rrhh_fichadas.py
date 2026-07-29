import pytest
from datetime import date, datetime, time

from app import create_app
from config import Config
from models import db
from models.hr.employee import Employee
from models.rrhh import FichadaReloj, ResumenAsistenciaDiaria, Turno, TurnoDia


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(Config, "SECRET_KEY", "test-secret")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "admin")
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr(Config, "WTF_CSRF_ENABLED", False)
    monkeypatch.setattr(Config, "RATELIMIT_ENABLED", False)
    monkeypatch.setattr(Config, "FLASK_ENV", "development")
    monkeypatch.setattr(Config, "DEBUG", False)

    app = create_app()
    app.config["TESTING"] = True

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def crear_turno_simple(nombre="Turno Manana"):
    turno = Turno(nombre=nombre, descripcion="Test", activo=True)
    db.session.add(turno)
    db.session.flush()
    db.session.add(
        TurnoDia(
            turno_id=turno.id,
            dia_semana=0,
            activo=True,
            es_cortado=False,
            hora_inicio_1=time(8, 0),
            hora_fin_1=time(17, 0),
        )
    )
    db.session.flush()
    return turno


def crear_empleado(first_name, last_name, *, clock_id=None, turno_id=None, is_active=True):
    empleado = Employee(
        first_name=first_name,
        last_name=last_name,
        clock_id=clock_id,
        turno_id=turno_id,
        is_active=is_active,
    )
    db.session.add(empleado)
    db.session.flush()
    return empleado


def crear_fichada(clock_id_original, fecha_hora, *, empleado_id=None, nombre_reloj="Reloj Test"):
    fichada = FichadaReloj(
        empleado_id=empleado_id,
        clock_id_original=clock_id_original,
        nombre_reloj=nombre_reloj,
        fecha=fecha_hora.date(),
        hora=fecha_hora.time(),
        fecha_hora=fecha_hora,
        archivo_origen="test.xlsx",
        lote_importacion="test-lote",
    )
    db.session.add(fichada)
    db.session.flush()
    return fichada


def test_fichadas_asociar_devuelve_diagnostico_cuando_no_hay_clock_ids(app, client):
    with app.app_context():
        crear_empleado("Ana", "Perez")
        crear_fichada("9", datetime(2026, 4, 20, 8, 0), nombre_reloj="ANA PEREZ")
        db.session.commit()

    resp = client.post("/api/rrhh/fichadas/asociar", json={})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["asociados"] == 0
    assert data["pendientes"] == 1
    assert data["diagnostico"]["empleados_con_clock_id"] == 0
    assert data["diagnostico"]["sin_match_total"] == 1
    assert data["diagnostico"]["sin_match"][0]["clock_id"] == "9"


def test_fichadas_asociar_reprocesa_resumen_diario(app, client):
    with app.app_context():
        turno = crear_turno_simple()
        empleado = crear_empleado("Carlos", "Salado", clock_id="9", turno_id=turno.id)
        empleado_id = empleado.id
        turno_id = turno.id
        crear_fichada("9", datetime(2026, 4, 20, 8, 5), nombre_reloj="CARLOS SALADO")
        crear_fichada("9", datetime(2026, 4, 20, 17, 0), nombre_reloj="CARLOS SALADO")
        db.session.commit()

    resp = client.post("/api/rrhh/fichadas/asociar", json={})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["asociados"] == 2
    assert data["pendientes"] == 0
    assert data["procesamiento"]["procesados"] == 1
    assert data["procesamiento"]["sin_turno"] == 0
    assert data["impactados"][0]["empleado"] == "Carlos Salado"

    with app.app_context():
        resumen = ResumenAsistenciaDiaria.query.one()
        assert resumen.empleado_id == empleado_id
        assert resumen.turno_id == turno_id
        assert resumen.fichadas_count == 2
        assert resumen.es_tarde is False


def test_fichadas_asociar_informa_empleados_sin_turno(app, client):
    with app.app_context():
        crear_empleado("Giselle", "Torti", clock_id="14", turno_id=None)
        crear_fichada("14", datetime(2026, 4, 20, 8, 0), nombre_reloj="GISELLE TORTI")
        db.session.commit()

    resp = client.post("/api/rrhh/fichadas/asociar", json={})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["asociados"] == 1
    assert data["pendientes"] == 0
    assert data["procesamiento"]["procesados"] == 0
    assert data["procesamiento"]["sin_turno"] == 1
    assert data["procesamiento"]["dias_sin_turno"] == 1

    with app.app_context():
        assert ResumenAsistenciaDiaria.query.count() == 0


def test_admin_empleado_normaliza_clock_id_y_permite_limpiar_campos(app, client):
    with app.app_context():
        turno = crear_turno_simple("Turno Tarde")
        empleado = crear_empleado("Jose", "More")
        empleado_id = empleado.id
        turno_id = turno.id
        db.session.commit()

    resp = client.put(
        f"/api/admin/rrhh/empleados/{empleado_id}",
        json={"clock_id": "009", "turno_id": turno_id},
    )
    assert resp.status_code == 200

    with app.app_context():
        empleado = Employee.query.get(empleado_id)
        assert empleado.clock_id == "9"
        assert empleado.turno_id == turno_id

    resp = client.put(
        f"/api/admin/rrhh/empleados/{empleado_id}",
        json={"clock_id": None, "turno_id": None},
    )
    assert resp.status_code == 200

    with app.app_context():
        empleado = Employee.query.get(empleado_id)
        assert empleado.clock_id is None
        assert empleado.turno_id is None


def test_admin_empleado_rechaza_clock_id_duplicado(app, client):
    with app.app_context():
        crear_empleado("Enzo", "Salado", clock_id="3")
        empleado = crear_empleado("Montserrat", "Martinez")
        empleado_id = empleado.id
        db.session.commit()

    resp = client.put(
        f"/api/admin/rrhh/empleados/{empleado_id}",
        json={"clock_id": "3"},
    )

    assert resp.status_code == 400
    data = resp.get_json()
    assert "ID Reloj" in data["error"]


def test_fichadas_resumen_calcula_sin_procesar_en_el_periodo_seleccionado(app, client):
    with app.app_context():
        empleado = crear_empleado("Francisco", "Gonzalez", clock_id="10")
        crear_fichada(
            "10",
            datetime(2026, 4, 20, 8, 0),
            empleado_id=empleado.id,
            nombre_reloj="FRANCISCO GONZALEZ",
        )
        crear_fichada(
            "10",
            datetime(2026, 3, 20, 8, 0),
            empleado_id=empleado.id,
            nombre_reloj="FRANCISCO GONZALEZ",
        )
        db.session.add(
            ResumenAsistenciaDiaria(
                empleado_id=empleado.id,
                fecha=date(2026, 3, 20),
                fichadas_count=1,
                fichadas_esperadas=2,
                es_falta=False,
                es_tarde=False,
                fichada_faltante=True,
                lote_importacion="manual",
            )
        )
        db.session.commit()

    resp = client.get("/api/rrhh/fichadas/resumen?periodo=2026-04")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["kpis"]["fichadas_sin_procesar"] == 1
    assert data["fichadas_sin_procesar_scope"] == "periodo"
