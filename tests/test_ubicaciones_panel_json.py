"""Alta de ubicaciones desde el panel lateral (SIS-2B, corte 3).

Cubre la rama JSON de /locations/new (201, 422 por campo, sin sesión, sin permiso, CSRF), el formulario
HTML que sigue con su redirect (302) y su aviso 400 (campo faltante), la edición clásica que no cambia,
el escape de textos con <, & y comillas, y el parcial de campos que comparten la página y el panel.
Datos sintéticos rotulados PROBE; SQLite en memoria.
"""

import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from models import Location, db
from models.core.user_permission import UserModulePermission
from sesion_de_prueba import asegurar_usuario, marcar_sesion

RAIZ = Path(__file__).resolve().parents[1]
JSON_ALTA = {"Accept": "application/json"}


def _cliente(app, usuario_id, usuario, rol):
    asegurar_usuario(app, usuario_id, usuario, rol)
    cliente = app.test_client()
    marcar_sesion(cliente, usuario_id)
    return cliente


def _alta_json(cliente, datos):
    return cliente.post("/locations/new", json=datos, headers=JSON_ALTA)


def test_alta_json_guarda_y_responde_201(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = _alta_json(cliente, {"name": "PROBE nave norte", "type": "nave"})

    assert respuesta.status_code == 201
    cuerpo = respuesta.get_json()
    assert cuerpo["ok"] is True
    assert cuerpo["nombre"] == "PROBE nave norte"
    assert cuerpo["tipo"] == "nave"
    assert isinstance(cuerpo["id"], int)
    fila = Location.query.one()
    assert fila.id == cuerpo["id"] and fila.name == "PROBE nave norte" and fila.type == "nave"


def test_alta_json_sin_nombre_devuelve_422_solo_en_name(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = _alta_json(cliente, {"type": "sucursal"})

    assert respuesta.status_code == 422
    cuerpo = respuesta.get_json()
    assert cuerpo["ok"] is False
    assert set(cuerpo["errors"]) == {"name"}
    assert cuerpo["errors"]["name"] == "Ingresá el nombre de la ubicación."
    assert Location.query.count() == 0


def test_alta_json_sin_tipo_devuelve_422_solo_en_type(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = _alta_json(cliente, {"name": "PROBE sin tipo"})

    assert respuesta.status_code == 422
    assert set(respuesta.get_json()["errors"]) == {"type"}
    assert Location.query.count() == 0


def test_alta_json_sin_campos_devuelve_422_en_ambos(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = _alta_json(cliente, {})

    assert respuesta.status_code == 422
    assert set(respuesta.get_json()["errors"]) == {"name", "type"}
    assert Location.query.count() == 0


def test_alta_json_sin_sesion_redirige_al_login_y_no_guarda(app_seguridad):
    anonimo = app_seguridad.test_client()

    respuesta = _alta_json(anonimo, {"name": "PROBE anonimo", "type": "nave"})

    assert respuesta.status_code == 302
    assert urlsplit(respuesta.location).path == "/"
    assert Location.query.count() == 0


def test_alta_json_con_permiso_de_solo_lectura_no_guarda(app_seguridad):
    cliente = _cliente(app_seguridad, 3, "PROBE-ventas-lectura", "sales")
    db.session.add(UserModulePermission(user_id=3, module="locations", access_level="view"))
    db.session.commit()

    respuesta = _alta_json(cliente, {"name": "PROBE lectura", "type": "nave"})

    assert respuesta.status_code == 403
    assert Location.query.count() == 0


def test_alta_json_sin_acceso_al_modulo_no_guarda(app_seguridad):
    cliente = _cliente(app_seguridad, 4, "PROBE-ventas-sin-modulo", "sales")

    respuesta = _alta_json(cliente, {"name": "PROBE sin modulo", "type": "nave"})

    assert respuesta.status_code == 302
    assert Location.query.count() == 0


def test_alta_json_sin_token_csrf_se_rechaza(app_seguridad, monkeypatch):
    monkeypatch.setitem(app_seguridad.config, "WTF_CSRF_CHECK_DEFAULT", True)
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = _alta_json(cliente, {"name": "PROBE csrf", "type": "nave"})

    assert respuesta.status_code == 400
    assert Location.query.count() == 0


def test_formulario_html_sigue_con_redirect_a_la_lista(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = cliente.post("/locations/new", data={"name": "PROBE html", "type": "sucursal"})

    assert respuesta.status_code == 302
    assert respuesta.location.endswith("/locations")
    fila = Location.query.one()
    assert fila.name == "PROBE html" and fila.type == "sucursal"


def test_formulario_html_sin_nombre_responde_400_con_aviso(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = cliente.post("/locations/new", data={"type": "nave"})

    assert respuesta.status_code == 400
    assert "Ingresá el nombre de la ubicación." in respuesta.get_data(as_text=True)
    assert Location.query.count() == 0


def test_formulario_html_sin_tipo_responde_400_con_aviso(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = cliente.post("/locations/new", data={"name": "PROBE sin tipo html"})

    assert respuesta.status_code == 400
    assert "Elegí el tipo de ubicación." in respuesta.get_data(as_text=True)
    assert Location.query.count() == 0


def test_edicion_clasica_sigue_igual(app_seguridad):
    fila = Location(name="PROBE antes", type="sucursal")
    db.session.add(fila)
    db.session.commit()
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    pagina = cliente.get(f"/locations/edit/{fila.id}").get_data(as_text=True)
    respuesta = cliente.post(
        f"/locations/edit/{fila.id}",
        data={"name": "PROBE despues", "type": "nave"},
    )

    assert 'value="PROBE antes"' in pagina
    assert '<option value="sucursal" selected>' in pagina
    assert respuesta.status_code == 302
    assert respuesta.location.endswith("/locations")
    db.session.refresh(fila)
    assert fila.name == "PROBE despues" and fila.type == "nave"


def test_get_new_muestra_los_campos_del_parcial(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    html = cliente.get("/locations/new").get_data(as_text=True)

    for marcado in (
        'id="ubicacion-nombre" name="name"',
        'id="ubicacion-tipo" name="type"',
        'data-error-campo="name"',
        'data-error-campo="type"',
    ):
        assert marcado in html


def test_panel_y_pagina_comparten_el_parcial(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    pagina = cliente.get("/locations/new").get_data(as_text=True)
    lista = cliente.get("/locations").get_data(as_text=True)

    assert 'id="ubicacionPanel"' in lista
    fragmento = 'id="ubicacion-nombre" name="name"'
    assert fragmento in pagina and fragmento in lista
    plantilla_pagina = (RAIZ / "templates" / "location_form.html").read_text(encoding="utf-8")
    plantilla_lista = (RAIZ / "templates" / "locations_list.html").read_text(encoding="utf-8")
    assert '"_location_form_campos.html"' in plantilla_pagina
    assert '"_location_form_campos.html"' in plantilla_lista
    assert (RAIZ / "templates" / "_location_form_campos.html").is_file()


def test_panel_lista_expone_guardar_y_agregar_otro_y_estado_vacio(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    lista = cliente.get("/locations").get_data(as_text=True)

    assert "Todavía no hay ubicaciones" in lista
    assert 'data-drawer-open="ubicacionPanel"' in lista
    assert 'data-accion="agregar"' in lista
    assert 'data-accion="guardar"' in lista


def test_fila_de_la_lista_expone_el_id_para_resaltar_el_alta(app_seguridad):
    fila = Location(name="PROBE fila", type="nave")
    db.session.add(fila)
    db.session.commit()
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    lista = cliente.get("/locations").get_data(as_text=True)

    assert f'data-location-id="{fila.id}"' in lista
    assert "data-locations-region" in lista


def test_nombres_con_marcado_y_comillas_se_escapan_en_lista_y_edicion(app_seguridad):
    nombre = 'PROBE <b>Dep & "Norte"</b>'
    fila = Location(name=nombre, type="nave")
    db.session.add(fila)
    db.session.commit()
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    lista = cliente.get("/locations").get_data(as_text=True)
    edicion = cliente.get(f"/locations/edit/{fila.id}").get_data(as_text=True)

    for html_publico in (lista, edicion):
        assert "PROBE <b>" not in html_publico
        assert "PROBE &lt;b&gt;Dep &amp; " in html_publico
        assert re.search(r"Norte&(quot|#34);", html_publico)


def test_alta_json_con_marcado_devuelve_texto_plano_y_la_lista_lo_escapa(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")
    nombre = 'PROBE <i>Tom & "Jerry"</i>'

    respuesta = _alta_json(cliente, {"name": nombre, "type": "nave"})
    lista = cliente.get("/locations").get_data(as_text=True)

    assert respuesta.status_code == 201
    assert respuesta.get_json()["nombre"] == nombre
    assert "PROBE <i>" not in lista
    assert "PROBE &lt;i&gt;Tom &amp; " in lista


def test_plantilla_de_ubicaciones_no_interpola_html_ni_usa_innerhtml():
    for nombre in ("locations_list.html", "_location_form_campos.html", "location_form.html"):
        plantilla = (RAIZ / "templates" / nombre).read_text(encoding="utf-8")
        assert "innerHTML" not in plantilla
        assert "outerHTML" not in plantilla
