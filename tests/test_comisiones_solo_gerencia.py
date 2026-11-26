"""Escribir comisiones es por rol: solo admin, manager y gerente. Datos sintéticos PROBE."""

from datetime import date

import pytest

from models import Client, Comision, Product, User, Venta, db
from models.core.user_permission import UserModulePermission
from sesion_de_prueba import marcar_sesion

CALCULAR = "/api/comercial/comisiones/calcular"
LISTAR = "/api/comercial/comisiones"


def _usuario(app, username, rol):
    u = User(username=username, role=rol, active=True)
    db.session.add(u)
    db.session.commit()
    c = app.test_client()
    marcar_sesion(c, u.id)
    return c, u.id


def _datos():
    cli = Client(name="PROBE-cliente")
    prod = Product(name="PROBE-producto", sku="PROBE-SKU-900")
    db.session.add_all([cli, prod])
    db.session.commit()
    db.session.add(Venta(fecha=date(2026, 10, 15), cliente_id=cli.id, producto_id=prod.id,
                         cantidad=2, precio_contrato=100, precio_efectivo=110))
    vend = User(username="PROBE-vend-base", role="sales", active=True)
    db.session.add(vend)
    db.session.commit()
    com = Comision(usuario_id=vend.id, periodo="2026-09", tipo_periodo="mensual", comision_total=10)
    db.session.add(com)
    db.session.commit()
    return com.id


def _escrituras(com_id):
    return [(CALCULAR, {"periodo": "2026-10"}), (f"{LISTAR}/{com_id}/pagar", {})]


@pytest.mark.parametrize("rol", ["sales", "operations", "viewer"])
def test_rol_no_administrativo_recibe_403_y_no_cambia_nada(app_seguridad, rol):
    com_id = _datos()
    cli, _ = _usuario(app_seguridad, f"PROBE-{rol}", rol)
    antes = Comision.query.count()
    for url, cuerpo in _escrituras(com_id):
        r = cli.post(url, json=cuerpo)
        assert r.status_code == 403, (rol, url)
    db.session.expire_all()
    assert Comision.query.count() == antes
    assert db.session.get(Comision, com_id).pagada in (False, None)


def test_excepcion_editar_comercial_no_habilita_escribir(app_seguridad):
    com_id = _datos()
    cli, uid = _usuario(app_seguridad, "PROBE-excepcion", "viewer")
    db.session.add(UserModulePermission(user_id=uid, module="comercial", access_level="edit"))
    db.session.commit()
    for url, cuerpo in _escrituras(com_id):
        assert cli.post(url, json=cuerpo).status_code == 403
    db.session.expire_all()
    assert db.session.get(Comision, com_id).pagada in (False, None)


@pytest.mark.parametrize("rol", ["admin", "manager", "gerente"])
def test_administracion_sigue_calculando_y_pagando(app_seguridad, rol):
    com_id = _datos()
    cli, _ = _usuario(app_seguridad, f"PROBE-{rol}", rol)
    assert cli.post(CALCULAR, json={"periodo": "2026-10"}).status_code == 200
    assert cli.post(CALCULAR, json={}).status_code == 400
    assert cli.post(f"{LISTAR}/{com_id}/pagar", json={}).status_code == 200
    assert cli.post(f"{LISTAR}/{com_id}/pagar", json={}).status_code == 400


def test_vendedor_sigue_leyendo_comisiones(app_seguridad):
    _datos()
    cli, _ = _usuario(app_seguridad, "PROBE-lector", "sales")
    assert cli.get(LISTAR).status_code == 200
