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


def test_cartera_30_dias_nuevo_por_vendedor_y_comparacion_no_filtrada(client, app):
    with app.app_context():
        agregar_pre(date(2024, 6, 18), "Ana Ruiz", "Cliente 40 días", importe=10, numero="C-40")
        agregar_pre(date(2024, 6, 18), "Otro vendedor", "Cliente nuevo para Ana", importe=10, numero="C-EMPRESA")
        agregar_pre(date(2024, 7, 18), "Ana Ruiz", "Cliente nuevo para Ana", importe=10, numero="C-ANA")
        agregar_pre(date(2024, 7, 18), "Ana Ruiz", "Cliente 10 días", importe=10, numero="C-10")
        agregar_pre(date(2024, 7, 23), "Ana Ruiz", "Cliente cartera", importe=90, producto="Producto A", numero="C-A")
        agregar_pre(date(2024, 7, 24), "Ana Ruiz", "Cliente compartido", importe=30, producto="Producto A", numero="C-SHARED-A")
        agregar_pre(date(2024, 7, 24), "WALTER", "Cliente Walter", importe=10, producto="Producto B", numero="C-W")
        agregar_pre(date(2024, 7, 25), "MEDINA WALTER", "Cliente compartido", importe=20, producto="Producto B", numero="C-SHARED-W")
        agregar_pre(date(2024, 7, 25), "Ana Ruiz", "Cliente cartera", importe=9999, producto="Producto LACTEOS", numero="L-1")
        db.session.query(StgSabiogoVentas).filter_by(codigo="L-1").update({StgSabiogoVentas.origen: "LACTEOS"})
        db.session.commit()

    base = "fecha_desde=2024-07-22&fecha_hasta=2024-07-28"
    todos = client.get(f"/api/dashboard-comercial/equipo?{base}&empresa=CARNES").get_json()["cartera"]
    assert todos["total_clientes"] == 6
    assert todos["clientes_nuevos_30d"] == 5

    ana = client.get(
        f"/api/dashboard-comercial/equipo?{base}&empresa=CARNES&vendedor=Ana%20Ruiz"
    )
    assert ana.status_code == 200
    cartera = ana.get_json()["cartera"]
    assert cartera["total_clientes"] == 5
    assert cartera["clientes_activos_30d"] == 4
    assert cartera["clientes_nuevos_30d"] == 4
    assert {row["cliente"] for row in cartera["clientes"]} == {
        "Cliente 40 días",
        "Cliente nuevo para Ana",
        "Cliente 10 días",
        "Cliente cartera",
        "Cliente compartido",
    }
    assert {row["vendedor"] for row in cartera["comparacion_vendedores"]} == {
        "Ana Ruiz",
        "Walter Medina",
    }
    participacion = {row["vendedor"]: row["participacion"] for row in cartera["comparacion_vendedores"]}
    assert participacion["Ana Ruiz"] == 80.0
    assert participacion["Walter Medina"] == 20.0
    assert cartera["productos"] == [{"nombre": "Producto A", "plata": 120.0, "pct": 100.0}]


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


def test_dashboard_separa_estrategia_de_seguimiento(client):
    response = client.get("/dashboard-comercial")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    titles = ["Resultado del período", "Evolución de ventas", "Objetivos del equipo", "Composición y concentración"]
    assert [html.index(title) for title in titles] == sorted(html.index(title) for title in titles)
    assert 'id="com-filtros"' in html
    assert 'id="cartera-clientes-body"' not in html
    assert 'id="com-clientes"' not in html
    assert "Análisis de cantidades" in html
    assert "Mix de ventas" in html
    assert 'id="cantidades-toggle" type="button" aria-expanded="true"' in html
    assert 'id="mix-toggle" type="button" aria-expanded="true"' in html
    assert 'id="com-performance"' not in html
    assert 'Ver seguimiento de clientes' in html


def test_analisis_cantidades_y_mix_respetan_medida_y_fecha_de_corte(client, app):
    with app.app_context():
        # SQLite no trae date_trunc; este UDF reproduce el agrupamiento mensual
        # para probar el contrato del endpoint con la base aislada del test.
        connection = db.engine.raw_connection()
        connection.create_function(
            "date_trunc",
            2,
            lambda unidad, valor: f"{str(valor)[:7]}-01" if unidad == "month" and valor else None,
        )
        connection.close()
        agregar_pre(date(2026, 1, 3), "Ana Ruiz", "Cliente", producto="Producto A", cajas=10, kilos=100, importe=500, numero="M-A")
        agregar_pre(date(2026, 1, 8), "Ana Ruiz", "Cliente", producto="Producto B", cajas=3, kilos=30, importe=300, numero="M-B")
        agregar_pre(date(2026, 1, 9), "Ana Ruiz", "Cliente", producto="Producto C", cajas=1, kilos=120, importe=2000, numero="M-C")
        agregar_pre(date(2026, 2, 1), "Ana Ruiz", "Cliente", producto="Producto futuro", cajas=1000, kilos=9999, importe=90000, numero="M-FUTURO")
        db.session.commit()

    filtros = "fecha_desde=2026-01-01&fecha_hasta=2026-01-31&empresa=CARNES"
    analisis = client.get(f"/api/dashboard-comercial/analisis?{filtros}&tipo=producto&medida=kilos")
    assert analisis.status_code == 200
    datos = analisis.get_json()
    assert datos["medida"] == "kilos"
    assert datos["top15"][0]["nombre"] == "Producto C"
    assert datos["top15"][0]["kilos"] == 120
    assert datos["evo_6m"][-1]["periodo"] == "2026-01"
    assert all(fila["kilos"] != 9999 for fila in datos["evo_6m"])

    mix = client.get(f"/api/dashboard-comercial/mix?{filtros}")
    assert mix.status_code == 200
    mix_datos = mix.get_json()
    assert all(fila["producto"] != "Producto futuro" for fila in mix_datos["mix_global"])
    assert mix_datos["evo_mix"][-1]["periodo"] == "2026-01"


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
