import importlib.util
from datetime import date
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from app import create_app
from config import Config
from models import db
from models.comercial import (
    ComercialObjetivo,
    ComercialObjetivoVinculo,
    ComercialVendedor,
)
from models.core.user import User
from models.hr.employee import Employee
from models.hr.goal import Goal
from models.sabiogo.staging import StgSabiogoVentas
from models.time_utils import today_local_date
from services.vendedores_comerciales import seed_vendedores_comerciales


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(Config, "SECRET_KEY", "test-secret")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "admin")
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr(Config, "WTF_CSRF_ENABLED", False)
    monkeypatch.setattr(Config, "RATELIMIT_ENABLED", False)

    app = create_app()
    app.config["TESTING"] = True

    with app.app_context():
        db.create_all()
        db.session.add(User(id=1, username="test-admin", role="admin", active=True))
        seed_vendedores_comerciales()
        db.session.add(
            ComercialVendedor(nombre_visible="Vendedor sin objetivo", activo=True)
        )
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _vendedor_id(app, nombre):
    with app.app_context():
        return db.session.query(ComercialVendedor).filter_by(nombre_visible=nombre).one().id


def _post_meta(client, vendedor_id, empresa, mes, medida, meta, **extra):
    data = {
        "vendedor_id": vendedor_id,
        "empresa": empresa,
        "mes": mes,
        "medida": medida,
        "meta": meta,
    }
    data.update(extra)
    return client.post("/api/objetivos-comerciales", json=data)


def _crear_goal(app, periodo="2025-06", meta=250.0, descripcion="Meta histórica"):
    with app.app_context():
        empleado = Employee(first_name="Ana", last_name="Legacy")
        db.session.add(empleado)
        db.session.flush()
        goal = Goal(
            employee_id=empleado.id,
            description=descripcion,
            period=periodo,
            target_value=meta,
            current_value=37.5,
            status="en progreso",
        )
        db.session.add(goal)
        db.session.commit()
        return goal.id, empleado.full_name


def _get_objetivo(client, mes, empresa, medida, vendedor_id, **extra):
    params = {
        "mes": mes,
        "empresa": empresa,
        "medida": medida,
        **extra,
    }
    response = client.get("/api/objetivos-comerciales", query_string=params)
    assert response.status_code == 200
    return next(
        item for item in response.get_json()["objetivos"]
        if item["vendedor_id"] == vendedor_id
    )


def _agregar_pre(app, vendedor, empresa, fecha, nro_comprob, importe, cajas=0, kilos=0):
    with app.app_context():
        db.session.add(
            StgSabiogoVentas(
                fecha=fecha,
                origen=empresa,
                sucursal="Central",
                tipo="A",
                codigo=f"PRE-{nro_comprob}",
                producto="Producto PRE",
                cliente="Cliente PRE",
                vendedor=vendedor,
                comprobante="PRE",
                nro_comprob=nro_comprob,
                subtot=importe,
                cajas=cajas,
                kilos=kilos,
                estado="procesado",
            )
        )
        db.session.commit()


def _mes_siguiente(hoy):
    year, month = hoy.year, hoy.month + 1
    if month == 13:
        year += 1
        month = 1
    return f"{year:04d}-{month:02d}"


def test_metas_por_empresa_misma_medida_son_independientes(client, app):
    vendedor_id = _vendedor_id(app, "Benjamín Kalja")
    mes = "2025-04"

    carnes = _post_meta(client, vendedor_id, "CARNES", mes, "importe", 1000)
    lacteos = _post_meta(client, vendedor_id, "LACTEOS", mes, "importe", 2500)

    assert carnes.status_code == 201
    assert lacteos.status_code == 201
    assert _get_objetivo(client, mes, "CARNES", "importe", vendedor_id)["meta"] == 1000.0
    assert _get_objetivo(client, mes, "LACTEOS", "importe", vendedor_id)["meta"] == 2500.0


def test_medidas_del_mismo_mes_son_independientes(client, app):
    vendedor_id = _vendedor_id(app, "Walter Medina")
    mes = "2025-05"

    importe = _post_meta(client, vendedor_id, "CARNES", mes, "importe", 5000)
    cajas = _post_meta(client, vendedor_id, "CARNES", mes, "cajas", 75)

    assert importe.status_code == 201
    assert cajas.status_code == 201
    assert _get_objetivo(client, mes, "CARNES", "importe", vendedor_id)["meta"] == 5000.0
    assert _get_objetivo(client, mes, "CARNES", "cajas", vendedor_id)["meta"] == 75.0


def test_get_recalcula_realizado_despues_de_insertar_pre(client, app):
    vendedor_id = _vendedor_id(app, "Benjamín Kalja")
    hoy = today_local_date()
    mes = hoy.strftime("%Y-%m")
    assert _post_meta(client, vendedor_id, "CARNES", mes, "importe", 100).status_code == 201

    _agregar_pre(
        app,
        "KALJA BENJAMIN",
        "CARNES",
        hoy,
        "PRE-MES-ACTUAL",
        125.5,
        cajas=2.5,
        kilos=25,
    )

    objetivo = _get_objetivo(client, mes, "CARNES", "importe", vendedor_id)
    assert objetivo["realizado"] == 125.5
    assert objetivo["cumplimiento"] == 1.255
    assert objetivo["estado"] == "Cumplido"
    assert objetivo["nota_ritmo"] == "El avance esperado es una referencia lineal, no un pronóstico."


def test_post_rechaza_realizado_y_duplicado_devuelve_409(client, app):
    vendedor_id = _vendedor_id(app, "Benjamín Kalja")
    base = {
        "vendedor_id": vendedor_id,
        "empresa": "CARNES",
        "mes": "2025-06",
        "medida": "importe",
        "meta": 100,
    }

    with_realizado = client.post(
        "/api/objetivos-comerciales",
        json={**base, "realizado": 50},
    )
    assert with_realizado.status_code == 400

    assert client.post("/api/objetivos-comerciales", json=base).status_code == 201
    duplicate = client.post("/api/objetivos-comerciales", json=base)
    assert duplicate.status_code == 409


def test_vendedor_sin_meta_aparece_sin_meta(client, app):
    vendedor_con_meta = _vendedor_id(app, "Benjamín Kalja")
    vendedor_sin_meta = _vendedor_id(app, "Walter Medina")
    mes = "2025-07"
    assert _post_meta(client, vendedor_con_meta, "CARNES", mes, "importe", 100).status_code == 201

    objetivo = _get_objetivo(client, mes, "CARNES", "importe", vendedor_sin_meta)
    assert objetivo["estado"] == "Sin meta"
    assert objetivo["meta"] is None
    assert objetivo["cumplimiento"] is None


def test_todas_informa_cobertura_incompleta_sin_porcentaje_global(client, app):
    vendedor_id = _vendedor_id(app, "Benjamín Kalja")
    mes = "2025-08"
    assert _post_meta(client, vendedor_id, "CARNES", mes, "importe", 100).status_code == 201

    objetivo = _get_objetivo(client, mes, "TODAS", "importe", vendedor_id)
    assert objetivo["cobertura"] == "incompleta"
    assert objetivo["estado"] == "Cobertura incompleta"
    assert objetivo["meta"] == 100.0
    assert objetivo["cumplimiento"] is None
    assert objetivo["desvio"] is None


def test_todas_calcula_cumplimiento_ponderado_sobre_suma(client, app):
    vendedor_id = _vendedor_id(app, "Benjamín Kalja")
    mes = "2025-09"
    assert _post_meta(client, vendedor_id, "CARNES", mes, "importe", 100).status_code == 201
    assert _post_meta(client, vendedor_id, "LACTEOS", mes, "importe", 300).status_code == 201
    _agregar_pre(app, "KALJA BENJAMIN", "CARNES", date(2025, 9, 12), "P-C-1", 50)
    _agregar_pre(app, "BENJAMIN KALJA", "LACTEOS", date(2025, 9, 12), "P-L-1", 300)

    objetivo = _get_objetivo(client, mes, "TODAS", "importe", vendedor_id)
    assert objetivo["cobertura"] == "completa"
    assert objetivo["realizado"] == 350.0
    assert objetivo["meta"] == 400.0
    assert objetivo["cumplimiento"] == 0.875


def test_mes_futuro_no_iniciado_mientras_mes_cerrado_no_cumplido(client, app):
    vendedor_id = _vendedor_id(app, "Benjamín Kalja")
    hoy = today_local_date()
    mes_futuro = _mes_siguiente(hoy)
    assert _post_meta(client, vendedor_id, "CARNES", mes_futuro, "importe", 100).status_code == 201
    assert _post_meta(client, vendedor_id, "CARNES", "2020-01", "importe", 100).status_code == 201

    futuro = _get_objetivo(
        client,
        mes_futuro,
        "CARNES",
        "importe",
        vendedor_id,
        fecha_corte=hoy.isoformat(),
    )
    cerrado = _get_objetivo(client, "2020-01", "CARNES", "importe", vendedor_id)
    assert futuro["estado"] == "No iniciado"
    assert futuro["avance_esperado"] == 0.0
    assert cerrado["estado"] == "No cumplido"
    assert cerrado["cumplimiento"] == 0.0


def test_patch_solo_edita_meta_y_descripcion(client, app):
    vendedor_id = _vendedor_id(app, "Walter Medina")
    response = _post_meta(client, vendedor_id, "LACTEOS", "2025-10", "kilos", 20)
    assert response.status_code == 201
    objetivo_id = response.get_json()["objetivo"]["id"]

    rechazo = client.patch(
        f"/api/objetivos-comerciales/{objetivo_id}",
        json={"realizado": 3},
    )
    assert rechazo.status_code == 400

    objetivo_db = ComercialObjetivo.query.filter_by(
        vendedor_id=vendedor_id,
        empresa="LACTEOS",
        mes="2025-10",
        medida="kilos",
    ).one()
    patch_response = client.patch(
        f"/api/objetivos-comerciales/{objetivo_db.id}",
        json={"meta": 30, "descripcion": "Meta revisada"},
    )
    assert patch_response.status_code == 200
    assert patch_response.get_json()["objetivo"]["meta"] == 30.0
    assert patch_response.get_json()["objetivo"]["descripcion"] == "Meta revisada"


def test_migracion_objetivos_crea_solo_esquema_en_sqlite_desechable():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "20261020_comercial_objetivos.py"
    )
    spec = importlib.util.spec_from_file_location(
        "comercial_objetivos_migration",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
            connection.exec_driver_sql(
                "CREATE TABLE comercial_vendedores (id INTEGER PRIMARY KEY)"
            )
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.upgrade()

            columnas = {
                column["name"]
                for column in inspect(connection).get_columns("comercial_objetivos")
            }
            assert {
                "vendedor_id",
                "empresa",
                "mes",
                "medida",
                "meta",
                "descripcion",
                "creado_en",
                "actualizado_en",
                "creado_por_id",
                "actualizado_por_id",
            } <= columnas
            assert connection.exec_driver_sql(
                "SELECT COUNT(*) FROM comercial_objetivos"
            ).scalar_one() == 0
    finally:
        engine.dispose()


def test_goal_se_convierte_solo_con_vendedor_empresa_y_medida_y_no_cambia(app, client):
    goal_id, nombre_empleado = _crear_goal(
        app,
        periodo="2025-06",
        meta=250,
        descripcion="Meta anterior premium",
    )
    vendedor_id = _vendedor_id(app, "Benjamín Kalja")
    completo = {
        "goal_id": goal_id,
        "vendedor_id": vendedor_id,
        "empresa": "CARNES",
        "medida": "importe",
    }
    pendiente_data = client.get("/api/objetivos-comerciales/pendientes").get_json()
    pendiente = next(
        item for item in pendiente_data["pendientes"] if item["goal_id"] == goal_id
    )
    assert pendiente["empleado"] == nombre_empleado
    assert pendiente["periodo"] == "2025-06"
    assert pendiente["mes_sugerido"] == "2025-06"
    assert pendiente["descripcion"] == "Meta anterior premium"
    assert pendiente["meta"] == 250.0

    for campo in ("vendedor_id", "empresa", "medida"):
        incompleto = {key: value for key, value in completo.items() if key != campo}
        assert client.post(
            "/api/objetivos-comerciales/convertir",
            json=incompleto,
        ).status_code == 400

    with app.app_context():
        assert ComercialObjetivo.query.count() == 0
        assert ComercialObjetivoVinculo.query.count() == 0

    respuesta = client.post("/api/objetivos-comerciales/convertir", json=completo)
    assert respuesta.status_code == 201
    datos = respuesta.get_json()
    assert datos["vinculo"]["goal_id"] == goal_id
    assert datos["objetivo"]["vendedor"] == "Benjamín Kalja"
    assert datos["objetivo"]["empresa"] == "CARNES"
    assert datos["objetivo"]["mes"] == "2025-06"
    assert datos["objetivo"]["medida"] == "importe"
    assert datos["objetivo"]["meta"] == 250.0
    assert datos["objetivo"]["descripcion"] == "Meta anterior premium"

    with app.app_context():
        original = db.session.get(Goal, goal_id)
        assert original.employee.full_name == nombre_empleado
        assert original.period == "2025-06"
        assert original.description == "Meta anterior premium"
        assert original.target_value == 250
        assert original.current_value == 37.5
        assert original.status == "en progreso"
        assert ComercialObjetivoVinculo.query.filter_by(goal_id=goal_id).count() == 1

    pendientes = client.get("/api/objetivos-comerciales/pendientes").get_json()
    assert goal_id not in {item["goal_id"] for item in pendientes["pendientes"]}
    assert {item["nombre_visible"] for item in pendientes["vendedores_comerciales"]} >= {
        "Benjamín Kalja",
        "Walter Medina",
    }


def test_convertir_el_mismo_goal_dos_veces_responde_409(app, client):
    goal_id, _ = _crear_goal(app, periodo="2025-07")
    payload = {
        "goal_id": goal_id,
        "vendedor_id": _vendedor_id(app, "Walter Medina"),
        "empresa": "LACTEOS",
        "medida": "kilos",
    }

    assert client.post("/api/objetivos-comerciales/convertir", json=payload).status_code == 201
    segunda = client.post("/api/objetivos-comerciales/convertir", json=payload)
    assert segunda.status_code == 409
    assert "convertido" in segunda.get_json()["error"].lower()
    with app.app_context():
        assert ComercialObjetivoVinculo.query.filter_by(goal_id=goal_id).count() == 1
        assert ComercialObjetivo.query.count() == 1


def test_meta_existente_no_se_duplica_y_goal_sigue_pendiente(app, client):
    vendedor_id = _vendedor_id(app, "Benjamín Kalja")
    assert _post_meta(client, vendedor_id, "CARNES", "2025-08", "cajas", 80).status_code == 201
    goal_id, _ = _crear_goal(app, periodo="2025-08", meta=80, descripcion="Meta original")
    payload = {
        "goal_id": goal_id,
        "vendedor_id": vendedor_id,
        "empresa": "CARNES",
        "medida": "cajas",
    }

    respuesta = client.post("/api/objetivos-comerciales/convertir", json=payload)
    assert respuesta.status_code == 409
    assert "meta" in respuesta.get_json()["error"].lower()
    assert "combinación" in respuesta.get_json()["error"].lower()

    with app.app_context():
        assert ComercialObjetivo.query.filter_by(
            vendedor_id=vendedor_id,
            empresa="CARNES",
            mes="2025-08",
            medida="cajas",
        ).count() == 1
        assert ComercialObjetivoVinculo.query.filter_by(goal_id=goal_id).count() == 0
        original = db.session.get(Goal, goal_id)
        assert original.current_value == 37.5
        assert original.status == "en progreso"
    pendientes = client.get("/api/objetivos-comerciales/pendientes").get_json()["pendientes"]
    assert goal_id in {item["goal_id"] for item in pendientes}


def test_periodo_legacy_no_yyyymm_requiere_mes_explicito(app, client):
    goal_id, _ = _crear_goal(app, periodo="2025-Q4")
    payload = {
        "goal_id": goal_id,
        "vendedor_id": _vendedor_id(app, "Benjamín Kalja"),
        "empresa": "LACTEOS",
        "medida": "importe",
    }
    assert client.post("/api/objetivos-comerciales/convertir", json=payload).status_code == 400
    assert ComercialObjetivoVinculo.query.filter_by(goal_id=goal_id).count() == 0

    respuesta = client.post(
        "/api/objetivos-comerciales/convertir",
        json={**payload, "mes": "2025-11"},
    )
    assert respuesta.status_code == 201
    assert respuesta.get_json()["objetivo"]["mes"] == "2025-11"


def test_migracion_vinculos_crea_esquema_vacio_en_sqlite_desechable():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "20261020_objetivo_vinculos.py"
    )
    spec = importlib.util.spec_from_file_location("objetivo_vinculos_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE goals (id INTEGER PRIMARY KEY)")
            connection.exec_driver_sql(
                "CREATE TABLE comercial_objetivos (id INTEGER PRIMARY KEY)"
            )
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.upgrade()

            constraints = inspect(connection).get_unique_constraints(
                "comercial_objetivo_vinculos"
            )
            assert {constraint["name"] for constraint in constraints} == {
                "uq_comercial_objetivo_vinculo_goal",
                "uq_comercial_objetivo_vinculo_objetivo",
            }
            assert connection.exec_driver_sql(
                "SELECT COUNT(*) FROM comercial_objetivo_vinculos"
            ).scalar_one() == 0
    finally:
        engine.dispose()


def test_pagina_objetivos_muestra_seccion_de_vinculacion(client, app):
    app.jinja_env.globals["csrf_token"] = lambda: "test-csrf"
    response = client.get("/comercial/objetivos")
    assert response.status_code == 200
    assert "Objetivos anteriores sin vincular" in response.get_data(as_text=True)
