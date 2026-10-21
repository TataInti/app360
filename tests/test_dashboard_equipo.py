from datetime import date

import pytest

from app import create_app
from config import Config
from models import db
from models.sabiogo.staging import StgSabiogoVentas
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
    app.jinja_env.globals["csrf_token"] = lambda: "test-csrf"
    with app.app_context():
        db.create_all()
        seed_vendedores_comerciales()
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def agregar_pre(fecha, vendedor, cliente, *, importe=100, cajas=1, kilos=10, producto="Producto", numero):
    db.session.add(
        StgSabiogoVentas(
            fecha=fecha,
            origen="CARNES",
            codigo=numero,
            producto=producto,
            cliente=cliente,
            vendedor=vendedor,
            subtot=importe,
            cajas=cajas,
            kilos=kilos,
            comprobante="PRE",
            nro_comprob=numero,
            estado="procesado",
        )
    )


def test_equipo_agrupa_aliases_y_sin_meta_no_es_cero_por_ciento(client, app):
    with app.app_context():
        agregar_pre(date(2024, 1, 5), "KALJA BENJAMIN", "Cliente compartido", numero="A-1")
        agregar_pre(date(2024, 1, 8), "BENJAMIN KALJA", "Cliente compartido", importe=50, numero="A-2")
        db.session.commit()

    response = client.get(
        "/api/dashboard-comercial/equipo?fecha_desde=2024-01-01&fecha_hasta=2024-01-31&empresa=CARNES"
    )
    assert response.status_code == 200
    data = response.get_json()
    filas = [fila for fila in data["equipo"] if fila["vendedor"] == "Benjamín Kalja"]
    assert len(filas) == 1
    assert filas[0]["realizado"] == 150.0
    assert filas[0]["estado"] == "Sin meta"
    assert filas[0]["cumplimiento"] is None
    assert filas[0]["clientes_compradores"] == 1


def test_vendedor_fuera_del_catalogo_conserva_el_realizado(client, app):
    with app.app_context():
        agregar_pre(date(2024, 2, 4), "Ana Ruiz", "Almacén Norte", importe=80, numero="B-1")
        agregar_pre(date(2024, 2, 9), "Ana Ruiz", "Almacén Norte", importe=20, numero="B-2")
        db.session.commit()

    response = client.get(
        "/api/dashboard-comercial/equipo?fecha_desde=2024-02-01&fecha_hasta=2024-02-29&empresa=CARNES"
    )
    assert response.status_code == 200
    filas = [fila for fila in response.get_json()["equipo"] if fila["vendedor"] == "Ana Ruiz"]
    assert len(filas) == 1
    assert filas[0]["estado"] == "Sin meta"
    assert filas[0]["realizado"] == 100.0
    assert filas[0]["cumplimiento"] is None


def test_atencion_devuelve_total_completo_y_pagina_de_20(client, app):
    with app.app_context():
        for indice in range(25):
            agregar_pre(
                date(2024, 5, 3),
                "KALJA BENJAMIN",
                f"Cliente {indice:02d}",
                numero=f"A-{indice:02d}",
            )
        db.session.commit()

    query = (
        "fecha_desde=2024-05-08&fecha_hasta=2024-05-14&empresa=CARNES"
        "&vendedor=Benjam%C3%ADn%20Kalja"
    )
    primera = client.get(f"/api/dashboard-comercial/equipo?{query}").get_json()
    segunda = client.get(f"/api/dashboard-comercial/equipo?{query}&pagina=2").get_json()

    assert primera["total_casos"] == 25
    assert primera["por_pagina"] == 20
    assert primera["pagina"] == 1
    assert len(primera["clientes_atencion"]) == 20
    assert segunda["total_casos"] == 25
    assert segunda["pagina"] == 2
    assert len(segunda["clientes_atencion"]) == 5
    assert all(row["vendedor"] == "Benjamín Kalja" for row in primera["clientes_atencion"])


def test_compra_posterior_al_corte_no_aparece_como_cliente_nuevo(client, app):
    with app.app_context():
        agregar_pre(
            date(2024, 5, 15),
            "WALTER",
            "Cliente Solo Futuro",
            numero="W-FUTURO",
        )
        db.session.commit()

    response = client.get(
        "/api/dashboard-comercial/equipo?fecha_desde=2024-05-08&fecha_hasta=2024-05-14"
        "&empresa=CARNES&vendedor=Walter%20Medina"
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["diagnostico"] is not None
    assert "Cliente Solo Futuro" not in {
        row["nombre"] for row in data["diagnostico"]["nuevos"]
    }
    assert data["estado_datos"] == "sin_operaciones"


def test_diagnostico_clasifica_clientes_y_compra_en_baja_indica_medida(client, app):
    with app.app_context():
        agregar_pre(date(2024, 6, 10), "KALJA BENJAMIN", "Cliente nuevo", numero="N-1")
        agregar_pre(date(2024, 6, 4), "BENJAMIN KALJA", "Cliente recurrente", numero="R-1")
        agregar_pre(date(2024, 6, 12), "KALJA BENJAMIN", "Cliente recurrente", numero="R-2")
        agregar_pre(date(2024, 5, 20), "KALJA BENJAMIN", "Cliente recuperado", numero="REC-0")
        agregar_pre(date(2024, 6, 11), "KALJA BENJAMIN", "Cliente recuperado", numero="REC-1")
        agregar_pre(date(2024, 6, 3), "KALJA BENJAMIN", "Cliente sin recompra", numero="S-1")
        agregar_pre(
            date(2024, 6, 5), "KALJA BENJAMIN", "Cliente baja", importe=1000,
            cajas=10, numero="B-1"
        )
        agregar_pre(
            date(2024, 6, 10), "KALJA BENJAMIN", "Cliente baja", importe=950,
            cajas=7, numero="B-2"
        )
        agregar_pre(date(2024, 6, 2), "KALJA BENJAMIN", "Cliente variedad", producto="P1", importe=100, numero="V-1")
        agregar_pre(date(2024, 6, 6), "KALJA BENJAMIN", "Cliente variedad", producto="P2", importe=100, numero="V-2")
        agregar_pre(date(2024, 6, 12), "KALJA BENJAMIN", "Cliente variedad", producto="P1", importe=180, numero="V-3")
        db.session.commit()

    response = client.get(
        "/api/dashboard-comercial/equipo?fecha_desde=2024-06-08&fecha_hasta=2024-06-14"
        "&empresa=CARNES&vendedor=Benjam%C3%ADn%20Kalja&medida=cajas"
    )
    assert response.status_code == 200
    data = response.get_json()
    diagnostico = data["diagnostico"]
    assert "Cliente nuevo" in {row["nombre"] for row in diagnostico["nuevos"]}
    assert "Cliente recurrente" in {row["nombre"] for row in diagnostico["recurrentes"]}
    assert "Cliente recuperado" in {row["nombre"] for row in diagnostico["recuperados"]}
    assert any(
        row["cliente"] == "Cliente baja" and row["senal"] == "Compra en baja" and row["medida"] == "cajas"
        for row in data["clientes_atencion"]
    )
    assert any(
        row["cliente"] == "Cliente variedad" and row["senal"] == "Menor variedad"
        for row in data["clientes_atencion"]
    )
    assert any(
        row["cliente"] == "Cliente sin recompra" and row["senal"] == "Sin recompra"
        for row in data["clientes_atencion"]
    )


def test_dashboard_renderiza_secciones_en_orden_y_mix_plegado(client):
    response = client.get("/dashboard-comercial")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Importe PRE" in html
    assert "Equipo comercial" in html
    assert "Diagnóstico de" in html
    assert "Clientes que requieren atención" in html
    assert 'data-period="mes"' in html
    assert 'id="analisis-body" style="padding:1rem;display:none"' in html
    assert 'id="mix-body" style="padding:1rem;display:none"' in html
    assert 'id="kpi-pre-top-vendedor"' not in html


def test_error_del_endpoint_equipo_no_devuelve_kpis_en_cero(client, monkeypatch):
    def fallar(*args, **kwargs):
        raise RuntimeError("fallo de prueba")

    monkeypatch.setattr("services.comercial_pre.calcular_resumen_pre", fallar)
    response = client.get(
        "/api/dashboard-comercial/equipo?fecha_desde=2024-01-01&fecha_hasta=2024-01-31"
    )

    assert response.status_code == 500
    data = response.get_json()
    assert "error" in data
    assert "kpis" not in data
