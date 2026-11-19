"""Recorrido E2E de la pantalla de objetivos comerciales (Playwright + Chromium real).

Requiere el entorno local levantado con `scripts/dev_preview/run_local.sh up`.
Entra por el formulario de login real, como cualquier usuario, y usa solo datos
sintéticos. Por defecto reinicia los datos sintéticos (`run_local.sh reset`) para
que cada corrida sea repetible; usá --sin-reset para conservar el estado actual.

Salida: capturas y un informe JSON en E2E_SHOTS_DIR (fuera del repo).
Código de salida: 0 si todas las verificaciones pasan; 1 si alguna falla.

Uso:
    scripts/dev_preview/run_local.sh up
    /root/.cache/app360-e2e-venv/bin/python scripts/dev_preview/e2e_objetivos.py
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlparse

from e2e_objetivos_helpers import (
    ObjetivosDOM,
    cantidad_lineas,
    comparar_borrado,
    comparar_linea_readback,
    entero,
    leer_objetivos,
    numero_visible,
    objetivo_devuelto,
    partir_real_meta,
    totales_equipo,
    vendedor_en,
)
from playwright.sync_api import expect, sync_playwright

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RUN_LOCAL = os.environ.get("E2E_RUN_LOCAL") or os.path.join(ROOT_DIR, "scripts", "dev_preview", "run_local.sh")
BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5055").rstrip("/")
ADMIN_USER = os.environ.get("E2E_ADMIN_USER", "admin")
# Clave de prueba SOLO-DEV del entorno E2E local (run_local.sh); no es una credencial real.
ADMIN_PASSWORD = os.environ.get("E2E_ADMIN_PASSWORD", "e2e-admin-ficticio")
CHROMIUM = os.environ.get(
    "E2E_CHROMIUM", "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
)
ZONA_LOCAL = timezone(timedelta(hours=-3))
MES = datetime.now(ZONA_LOCAL).strftime("%Y-%m")
SHOTS_DIR = os.environ.get("E2E_SHOTS_DIR") or os.path.join(
    "/root/.hermes/cache/scratch/e2e-shots", f"objetivos-{datetime.now(ZONA_LOCAL):%Y%m%dT%H%M%S}"
)

# Contraseñas ficticias de los usuarios sembrados por seed_demo.py.
CLAVES_ROL = {
    "ventas.demo": "e2e-ventas-ficticia",
    "rrhh.demo": "e2e-rrhh-ficticia",
    "finanzas.demo": "e2e-finanzas-ficticia",
}

ANA = "Vendedora Demo Ana"
BRUNO = "Vendedor Demo Bruno"
CARLA = "Vendedora Demo Carla"
DIEGO = "Vendedor Demo Diego"
NUEVA = "Vendedora Demo Nueva"

# Un caso por nivel: texto a escribir, opción esperada e importe a cargar.
NIVELES = [
    {"nivel": "empresa", "consulta": "CAR", "esperada": "CARNES", "importe": "100000"},
    {"nivel": "rubro", "consulta": "teos", "esperada": "Lácteos", "importe": "110000"},
    {"nivel": "subrubro", "consulta": "duros", "esperada": "Quesos duros", "importe": "120000"},
    {"nivel": "marca", "consulta": "Norte", "esperada": "Marca Norte", "importe": "130000"},
    {
        "nivel": "producto",
        "consulta": "Sardo",
        "esperada": "Queso Sardo Demo 1kg",
        "importe": "140000",
    },
]


class Informe:
    def __init__(self):
        self.verificaciones = []
        self.errores_pagina = []
        self.respuestas = []

    def verificar(self, nombre, ok, detalle=""):
        ok = bool(ok)
        self.verificaciones.append({"nombre": nombre, "ok": ok, "detalle": str(detalle)[:400]})
        marca = "OK   " if ok else "FALLA"
        sufijo = f" -- {str(detalle)[:200]}" if detalle != "" else ""
        print(f"{marca} {nombre}{sufijo}", flush=True)
        return ok

    def guardar(self, ruta):
        fallas = [v for v in self.verificaciones if not v["ok"]]
        with open(ruta, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "base_url": BASE_URL,
                    "mes": MES,
                    "total": len(self.verificaciones),
                    "fallas": len(fallas),
                    "verificaciones": self.verificaciones,
                    "errores_consola_o_pagina": self.errores_pagina,
                    "respuestas_api": self.respuestas,
                },
                fh,
                ensure_ascii=False,
                indent=2,
            )
        return len(self.verificaciones), len(fallas)


def normalizar(texto):
    return re.sub(r"\s+", " ", (texto or "")).strip()


def login(page, usuario, clave):
    page.goto(BASE_URL + "/", wait_until="domcontentloaded")
    page.fill("#username", usuario)
    page.fill("#password", clave)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")
    return urlparse(page.url).path != "/"


def instrumentar(page, informe):
    page.on(
        "pageerror",
        lambda e: informe.errores_pagina.append({"tipo": "excepcion", "texto": str(e)[:300]}),
    )
    page.on(
        "console",
        lambda m: (
            informe.errores_pagina.append({"tipo": "consola", "texto": m.text[:300]})
            if m.type == "error"
            else None
        ),
    )

    def al_responder(respuesta):
        ruta = urlparse(respuesta.url)
        interesa = (
            respuesta.status >= 400 or respuesta.request.method != "GET" or "/opciones" in ruta.path
        )
        if interesa:
            informe.respuestas.append(
                {
                    "metodo": respuesta.request.method,
                    "ruta": ruta.path + (f"?{ruta.query}" if ruta.query else ""),
                    "estado": respuesta.status,
                }
            )

    page.on("response", al_responder)


def esperar_carga(page):
    page.wait_for_selector("#objetivosCarga[hidden]", state="attached", timeout=20000)


def esperar_opciones(dropdown, segundos=8):
    """Devuelve 'opciones', 'sin-resultados' o 'timeout' según lo que muestre el desplegable."""
    limite = time.time() + segundos
    while time.time() < limite:
        if dropdown.locator(".option").count() > 0:
            return "opciones"
        if dropdown.locator(".no-results").count() > 0:
            return "sin-resultados"
        time.sleep(0.15)
    return "timeout"


def item_seleccionado(linea):
    items = linea.locator(".ts-control .item")
    return normalizar(items.first.inner_text()) if items.count() else ""


def campo_busqueda(contenedor):
    """Campo de búsqueda de TomSelect. El plugin dropdown_input lo mueve dentro del desplegable;
    `.ts-control input` apunta al input de marcador (items-placeholder), que nunca recibe foco."""
    return contenedor.locator("input.dropdown-input").first


def abrir_control(page, contenedor):
    """Abre el desplegable de TomSelect y espera el foco en su campo de búsqueda.

    Si ya está abierto, hacer clic en el control lo cerraría: en ese caso se enfoca el campo."""
    dropdown = contenedor.locator(".ts-dropdown").first
    if dropdown.is_visible():
        campo_busqueda(contenedor).click()
    else:
        contenedor.locator(".ts-control").first.click()
    expect(campo_busqueda(contenedor)).to_be_focused(timeout=5000)


def esperar_filtro(dropdown, consulta, segundos=5):
    """Espera a que las opciones visibles coincidan con la consulta; devuelve sus textos."""
    limite = time.time() + segundos
    textos = []
    while time.time() < limite:
        textos = [normalizar(t) for t in dropdown.locator(".option").all_inner_texts() if t.strip()]
        if textos and all(consulta.lower() in t.lower() for t in textos):
            break
        time.sleep(0.15)
    return textos


def opcion(contenedor, texto):
    return contenedor.locator(".ts-dropdown").first.locator(".option", has_text=texto).first


def enviar_linea(page, linea, metodo, patron):
    """Envía el formulario de la línea y devuelve la respuesta de la petición indicada."""
    with page.expect_response(
        lambda r: r.request.method == metodo and patron in r.url, timeout=15000
    ) as info:
        linea.locator("button[type=submit]").click()
    return info.value


def tomar(page, carpeta, nombre):
    os.makedirs(carpeta, exist_ok=True)
    page.screenshot(path=os.path.join(carpeta, nombre + ".png"), full_page=True)


def recorrido_permisos(navegador, informe):
    print("== Permisos por rol", flush=True)
    for usuario, clave in CLAVES_ROL.items():
        contexto = navegador.new_context(viewport={"width": 1280, "height": 900})
        page = contexto.new_page()
        ingreso = login(page, usuario, clave)
        informe.verificar(f"login {usuario} por formulario", ingreso, urlparse(page.url).path)
        # Sin seguir redirecciones: una redirección a la pantalla permitida no es un dato.
        estado = contexto.request.get(
            f"{BASE_URL}/api/objetivos-comerciales?mes={MES}&medida=importe", max_redirects=0
        ).status
        page.goto(BASE_URL + "/comercial/objetivos", wait_until="domcontentloaded")
        if usuario == "ventas.demo":
            informe.verificar(
                "ventas.demo puede abrir objetivos",
                page.locator("#listaVendedores").count() == 1 and estado == 200,
                f"API {estado}",
            )
        else:
            informe.verificar(f"{usuario} no lee objetivos por API", estado != 200, f"API {estado}")
            informe.verificar(
                f"{usuario} no ve la pantalla de objetivos",
                page.locator("#listaVendedores").count() == 0,
                urlparse(page.url).path,
            )
        contexto.close()


def recorrido_admin(page, informe, carpeta, contexto):
    print("== Pantalla de objetivos (admin)", flush=True)
    ui = ObjetivosDOM(page)
    page.goto(BASE_URL + "/comercial/objetivos", wait_until="domcontentloaded")
    esperar_carga(page)
    page.locator("#periodoMes").select_option(MES[5:7])
    page.locator("#periodoAnio").select_option(MES[:4])
    page.dispatch_event("#periodoObjetivos", "change")
    esperar_carga(page)
    page.wait_for_timeout(400)
    tomar(page, carpeta, "01-pagina")
    tarjetas = ui.filas_vendedor().count()
    informe.verificar("la pantalla carga las tarjetas del período", tarjetas >= 3, tarjetas)

    # Alta de vendedor desde el catálogo.
    page.click("#agregarVendedor")
    abrir_control(page, ui.borrador_vendedor())
    page.keyboard.type(DIEGO)
    opcion_diego = page.locator(".ts-dropdown:visible .option", has_text=DIEGO).first
    expect(opcion_diego).to_be_visible(timeout=8000)
    opcion_diego.click()
    page.wait_for_timeout(300)
    referencia = ui.borrador_vendedor().evaluate("e => e.dataset.vendedorRef || ''")
    informe.verificar(
        "alta de vendedor desde el catálogo", referencia.startswith("id:"), referencia
    )

    # Cada nivel: abrir sin escribir, buscar, elegir, guardar.
    for caso in NIVELES:
        nivel = caso["nivel"]
        print(f"-- nivel {nivel}", flush=True)
        tarjeta = ui.tarjeta_activa(DIEGO)
        tarjeta.locator("[data-add-line]").click()
        linea = ui.formulario_alta(DIEGO)
        valor = ui.campo_alta("valor")
        elegir_nivel(page, nivel)
        page.wait_for_timeout(300)
        abrir_control(page, valor)
        dropdown = valor.locator(".ts-dropdown").first
        estado = esperar_opciones(dropdown)
        informe.verificar(
            f"[{nivel}] abrir sin escribir muestra opciones", estado == "opciones", estado
        )
        tomar(page, carpeta, f"02-{nivel}-abrir-sin-escribir")

        page.keyboard.type(caso["consulta"])
        textos = esperar_filtro(dropdown, caso["consulta"])
        hallada = caso["esperada"] in textos
        solo_coincidencias = all(caso["consulta"].lower() in t.lower() for t in textos)
        informe.verificar(
            f"[{nivel}] buscar «{caso['consulta']}» filtra y muestra «{caso['esperada']}»",
            hallada and solo_coincidencias,
            textos[:6],
        )
        if hallada:
            dropdown.locator(".option", has_text=caso["esperada"]).first.click()
            page.wait_for_timeout(300)
        seleccion = item_seleccionado(valor)
        informe.verificar(
            f"[{nivel}] la selección queda elegida", seleccion == caso["esperada"], seleccion
        )
        tomar(page, carpeta, f"03-{nivel}-elegido")

        meta_cajas = 0
        meta_kilos = 0
        if nivel == "producto":
            linea.locator('[data-meta="importe"]').fill("0")
            linea.locator("button[type=submit]").click()
            page.wait_for_timeout(900)
            aviso = linea.locator("[data-line-error]")
            texto_aviso = normalizar(aviso.inner_text()) if aviso.count() else ""
            informe.verificar(
                "producto sin metas: el aviso aparece en la línea",
                aviso.is_visible() and texto_aviso != "",
                texto_aviso,
            )
            informe.verificar(
                "producto sin metas: el aviso indica qué falta (importe, cajas o kilos)",
                aviso.is_visible() and "importe" in texto_aviso.lower(),
                texto_aviso,
            )
            tomar(page, carpeta, "04-producto-aviso-metas")
            informe.verificar(
                "producto con cantidades: cajas y kilos habilitados",
                linea.locator('[data-meta="cajas"]').is_enabled()
                and linea.locator('[data-meta="kilos"]').is_enabled(),
            )
            abrir_control(page, valor)
            page.keyboard.type("Ricota")
            expect(opcion(valor, "Ricota")).to_be_visible(timeout=8000)
            opcion(valor, "Ricota").click()
            page.wait_for_timeout(300)
            informe.verificar(
                "producto sin cantidades: cajas y kilos deshabilitados",
                linea.locator('[data-meta="cajas"]').is_disabled()
                and linea.locator('[data-meta="kilos"]').is_disabled(),
                item_seleccionado(valor),
            )
            abrir_control(page, valor)
            page.keyboard.type(caso["consulta"])
            expect(opcion(valor, caso["esperada"])).to_be_visible(timeout=8000)
            opcion(valor, caso["esperada"]).click()
            page.wait_for_timeout(300)
            linea.locator('[data-meta="cajas"]').fill("10")
            linea.locator('[data-meta="kilos"]').fill("20")
            meta_cajas = 10
            meta_kilos = 20

        linea.locator('[data-meta="importe"]').fill(caso["importe"])
        datos_antes = leer_objetivos(contexto, BASE_URL, MES)
        lineas_antes = cantidad_lineas(datos_antes, nombre=DIEGO)
        respuesta = enviar_linea(page, linea, "POST", "/api/objetivos-comerciales")
        informe.verificar(
            f"[{nivel}] guardar la línea responde 201",
            respuesta.status == 201,
            f"{respuesta.status} {respuesta.text()[:150]}",
        )
        esperar_carga(page)
        page.wait_for_timeout(300)
        objetivo_post = objetivo_devuelto(respuesta)
        datos_despues = leer_objetivos(contexto, BASE_URL, MES)
        readback_ok, readback_detalle = comparar_linea_readback(
            datos_despues,
            objetivo_post.get("id"),
            {
                "importe": int(caso["importe"]),
                "cajas": meta_cajas,
                "kilos": meta_kilos,
            },
            lineas_antes + (1 if respuesta.status == 201 else 0),
            vendedor_id=objetivo_post.get("vendedor_id"),
        )
        informe.verificar(
            f"[{nivel}] readback API confirma id, metas y cantidad de líneas",
            readback_ok,
            readback_detalle,
        )
        visibles = ui.lineas_de(DIEGO).filter(has_text=caso["esperada"]).count()
        informe.verificar(
            f"[{nivel}] la línea guardada aparece en la tarjeta", visibles >= 1, visibles
        )
        tomar(page, carpeta, f"05-{nivel}-guardado")

    # Edición de una línea existente (Ana).
    print("-- editar y eliminar líneas", flush=True)
    datos_ana_antes = leer_objetivos(contexto, BASE_URL, MES)
    ana_antes = vendedor_en(datos_ana_antes, nombre=ANA)
    if ana_antes is None or not ana_antes.get("lineas"):
        raise AssertionError("El readback previo no encontró líneas de Ana")
    linea_ana_json = ana_antes["lineas"][0]
    ui.expandir(ANA)
    linea_ana = ui.linea(ANA, line_id=linea_ana_json["id"])
    metas_ana_esperadas = dict(linea_ana_json["metas"])
    metas_ana_esperadas["importe"] = 1600000
    cantidad_ana_antes = ana_antes["cantidad_lineas"]
    linea_ana.locator('[data-meta="importe"]').fill("1600000")
    respuesta = enviar_linea(page, linea_ana, "PATCH", "/api/objetivos-comerciales/")
    informe.verificar(
        "editar línea existente responde 200",
        respuesta.status == 200,
        f"{respuesta.status} {respuesta.text()[:150]}",
    )
    esperar_carga(page)
    page.wait_for_timeout(300)
    datos_ana_despues = leer_objetivos(contexto, BASE_URL, MES)
    readback_ok, readback_detalle = comparar_linea_readback(
        datos_ana_despues,
        linea_ana_json["id"],
        metas_ana_esperadas,
        cantidad_ana_antes,
        vendedor_id=ana_antes["vendedor_id"],
    )
    informe.verificar(
        "readback API confirma la edición de id, metas y cantidad de líneas",
        readback_ok,
        readback_detalle,
    )
    resumen = normalizar(ui.resumen_de(ANA).inner_text())
    informe.verificar(
        "la edición queda reflejada en el resumen del vendedor",
        "1.600.000" in resumen,
        resumen[:160],
    )
    tomar(page, carpeta, "06-editar-linea")

    # Eliminación de una línea existente (Carla).
    datos_carla_antes = leer_objetivos(contexto, BASE_URL, MES)
    carla_antes = vendedor_en(datos_carla_antes, nombre=CARLA)
    if carla_antes is None or not carla_antes.get("lineas"):
        raise AssertionError("El readback previo no encontró líneas de Carla")
    linea_carla_json = carla_antes["lineas"][0]
    antes = ui.lineas_de(CARLA).count()
    ui.expandir(CARLA)
    ui.linea(CARLA, line_id=linea_carla_json["id"]).locator("[data-delete-line]").click()
    confirmar = page.get_by_role("button", name="Eliminar", exact=True).last
    expect(confirmar).to_be_visible(timeout=5000)
    with page.expect_response(
        lambda r: r.request.method == "DELETE" and "/api/objetivos-comerciales/" in r.url,
        timeout=15000,
    ) as info:
        confirmar.click()
    informe.verificar("eliminar línea responde 200", info.value.status == 200, info.value.status)
    esperar_carga(page)
    page.wait_for_timeout(300)
    datos_carla_despues = leer_objetivos(contexto, BASE_URL, MES)
    readback_ok, readback_detalle = comparar_borrado(
        datos_carla_antes,
        datos_carla_despues,
        carla_antes["vendedor_id"],
        linea_carla_json["id"],
        carla_antes["cantidad_lineas"] - (1 if info.value.status == 200 else 0),
    )
    informe.verificar(
        "readback API confirma id eliminado, metas restantes y cantidad de líneas",
        readback_ok,
        readback_detalle,
    )
    despues = ui.lineas_de(CARLA).count()
    informe.verificar(
        "eliminar línea la quita de la tarjeta", despues == antes - 1, f"{antes}->{despues}"
    )

    # Convertir objetivos históricos de RRHH.
    print("-- convertir objetivos históricos de RRHH", flush=True)
    page.locator("details.oc-legacy summary").click()
    filas = page.locator("#legacyGoals tbody tr")
    expect(filas.first).to_be_visible(timeout=8000)
    total_inicial = filas.count()
    tomar(page, carpeta, "07-historicos-antes")

    page.locator("#legacyGoals tbody tr").filter(has_text="2026-09").first.locator(
        "form[data-convert-form] button[type=submit]"
    ).click()
    page.wait_for_timeout(900)
    aviso_legacy = page.locator("#legacyError")
    texto_legacy = normalizar(aviso_legacy.inner_text()) if aviso_legacy.count() else ""
    informe.verificar(
        "convertir sin vendedor avisa en pantalla",
        aviso_legacy.is_visible() and texto_legacy != "",
        texto_legacy,
    )

    fila_q4 = page.locator("#legacyGoals tbody tr").filter(has_text="2026-Q4").first
    form_q4 = fila_q4.locator("form[data-convert-form]")
    if fila_q4.locator("select[data-month-mes]").count():
        fila_q4.locator("select[data-month-mes]").select_option(MES[5:7])
        fila_q4.locator("select[data-month-anio]").select_option(MES[:4])
    abrir_control(page, form_q4)
    page.keyboard.type(DIEGO)
    expect(page.locator(".ts-dropdown:visible .option", has_text=DIEGO).first).to_be_visible(
        timeout=8000
    )
    page.locator(".ts-dropdown:visible .option", has_text=DIEGO).first.click()
    form_q4.locator("select[data-company]").select_option("LACTEOS")
    form_q4.locator("select[data-measure]").select_option("kilos")
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/api/objetivos-comerciales/convertir" in r.url,
        timeout=15000,
    ) as info:
        form_q4.locator("button[type=submit]").click()
    informe.verificar(
        "convertir período trimestral con mes elegido responde 201",
        info.value.status == 201,
        f"{info.value.status} {info.value.text()[:120]}",
    )
    esperar_carga(page)
    page.wait_for_timeout(600)

    fila_oct = page.locator("#legacyGoals tbody tr").filter(has_text="2026-10").first
    form_oct = fila_oct.locator("form[data-convert-form]")
    abrir_control(page, form_oct)
    page.keyboard.type(ANA)
    expect(page.locator(".ts-dropdown:visible .option", has_text=ANA).first).to_be_visible(
        timeout=8000
    )
    page.locator(".ts-dropdown:visible .option", has_text=ANA).first.click()
    form_oct.locator("select[data-company]").select_option("CARNES")
    form_oct.locator("select[data-measure]").select_option("importe")
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/api/objetivos-comerciales/convertir" in r.url,
        timeout=15000,
    ) as info:
        form_oct.locator("button[type=submit]").click()
    informe.verificar(
        "convertir período mensual responde 201", info.value.status == 201, info.value.status
    )
    esperar_carga(page)
    page.wait_for_timeout(600)
    quedan = page.locator("#legacyGoals tbody tr").count()
    informe.verificar(
        "las dos conversiones salen de la lista de pendientes",
        quedan == total_inicial - 2,
        f"{total_inicial}->{quedan}",
    )
    tomar(page, carpeta, "08-historicos-despues")

    # Vendedor nuevo por nombre (no está en el catálogo).
    print("-- vendedor nuevo por nombre", flush=True)
    page.click("#agregarVendedor")
    abrir_control(page, ui.borrador_vendedor())
    page.keyboard.type(NUEVA)
    page.wait_for_timeout(400)
    page.keyboard.press("Enter")
    page.wait_for_timeout(400)
    referencia = ui.borrador_vendedor().evaluate("e => e.dataset.vendedorRef || ''")
    informe.verificar(
        "vendedor nuevo queda seleccionado por nombre", referencia == f"nombre:{NUEVA}", referencia
    )
    ui.zona_de(ui.borrador_vendedor()).locator("[data-add-line]").click()
    linea_nueva = ui.formulario_alta(NUEVA)
    elegir_nivel(page, "marca")
    page.wait_for_timeout(300)
    abrir_control(page, ui.campo_alta("valor"))
    page.keyboard.type("Campo")
    expect(opcion(ui.campo_alta("valor"), "Campo Demo")).to_be_visible(timeout=8000)
    opcion(ui.campo_alta("valor"), "Campo Demo").click()
    page.wait_for_timeout(300)
    linea_nueva.locator('[data-meta="importe"]').fill("80000")
    datos_nueva_antes = leer_objetivos(contexto, BASE_URL, MES)
    lineas_nueva_antes = cantidad_lineas(datos_nueva_antes, nombre=NUEVA)
    respuesta = enviar_linea(page, linea_nueva, "POST", "/api/objetivos-comerciales")
    informe.verificar(
        "alta con vendedor nuevo responde 201",
        respuesta.status == 201,
        f"{respuesta.status} {respuesta.text()[:140]}",
    )
    esperar_carga(page)
    page.wait_for_timeout(300)
    objetivo_nuevo = objetivo_devuelto(respuesta)
    datos_nueva_despues = leer_objetivos(contexto, BASE_URL, MES)
    readback_ok, readback_detalle = comparar_linea_readback(
        datos_nueva_despues,
        objetivo_nuevo.get("id"),
        {"importe": 80000, "cajas": 0, "kilos": 0},
        lineas_nueva_antes + (1 if respuesta.status == 201 else 0),
        vendedor_id=objetivo_nuevo.get("vendedor_id"),
    )
    informe.verificar(
        "readback API confirma alta por nombre: id, metas y cantidad de líneas",
        readback_ok,
        readback_detalle,
    )
    informe.verificar(
        "el vendedor nuevo aparece como tarjeta", ui.fila_vendedor(NUEVA).count() == 1
    )
    tomar(page, carpeta, "09-vendedor-nuevo")
    informe.verificar(
        "la pantalla termina sin error de carga", page.locator("#objetivosError").is_hidden()
    )


JS_CELDAS = r"tr => [...tr.children].map(c => c.innerText.replace(/\s+/g, ' ').trim())"

JS_MEDIDAS = """() => {
  const wrap = document.querySelector('.oc-team-wrap');
  const tabla = document.querySelector('.oc-team');
  const filas = [...document.querySelectorAll('tr[data-seller-row]')].filter(f => !f.hasAttribute('data-seller-draft'));
  const sexta = filas[Math.min(5, filas.length - 1)];
  const pie = document.querySelector('.oc-team tfoot');
  const numericas = [...document.querySelectorAll('.oc-team tbody td.num')];
  return {
    filas: filas.length,
    tabla_inferior: Math.round(tabla.getBoundingClientRect().bottom),
    seis_contraidos_inferior: Math.round(sexta.getBoundingClientRect().bottom + pie.getBoundingClientRect().height),
    alto: window.innerHeight,
    scroll_horizontal: wrap.scrollWidth - wrap.clientWidth,
    numericas_derecha: numericas.length > 0 && numericas.every(td => getComputedStyle(td).textAlign === 'right'),
    contraidas: filas.length > 0 && filas.every(f => f.nextElementSibling && f.nextElementSibling.hidden),
  };
}"""


def recorrido_tabla_equipo(page, informe, carpeta, contexto):
    """Tabla de equipo: fila Equipo, filas, expandir y contraer, borradores y medidas.

    La fuente de verdad es el GET de objetivos del mes; la pantalla se compara contra esa lectura.
    Con SEED_EQUIPO=1 también se verifica a T-Elena, vendedora sin líneas del seed de equipo.
    """
    print("== Tabla de equipo", flush=True)
    ui = ObjetivosDOM(page)
    page.goto(BASE_URL + "/comercial/objetivos", wait_until="domcontentloaded")
    esperar_carga(page)
    page.wait_for_timeout(300)
    datos = leer_objetivos(contexto, BASE_URL, MES)
    filas = ui.filas_vendedor()
    con_equipo = bool(os.environ.get("SEED_EQUIPO"))
    if con_equipo:
        informe.verificar(
            "sin líneas: T-Elena no aparece al cargar la pantalla",
            ui.fila_vendedor("T-Elena").count() == 0,
        )

    # Fila Equipo: suma de la API. Cada medida solo suma a los vendedores con meta en esa medida.
    total = totales_equipo(datos)

    def partir_esperado(medida):
        if not total[medida]["hay"]:
            return (None, None)
        return (entero(total[medida]["real"]), entero(total[medida]["meta"]))

    avance_equipo = None
    if total["importe"]["hay"] and total["importe"]["meta"] > 0:
        avance_equipo = entero(total["importe"]["real"] / total["importe"]["meta"] * 100)
    esperado_equipo = {
        "lineas": total["lineas"],
        "importe_meta": entero(total["importe"]["meta"]) if total["importe"]["hay"] else None,
        "importe_real": entero(total["importe"]["real"]) if total["importe"]["hay"] else None,
        "cajas": partir_esperado("cajas"),
        "kilos": partir_esperado("kilos"),
        "avance": avance_equipo,
    }
    dom_equipo = {
        "lineas": numero_visible(page.locator("#equipoLineas").inner_text()),
        "importe_meta": numero_visible(page.locator("#equipoMeta").inner_text()),
        "importe_real": numero_visible(page.locator("#equipoReal").inner_text()),
        "cajas": partir_real_meta(page.locator("#equipoCajas").inner_text()),
        "kilos": partir_real_meta(page.locator("#equipoKilos").inner_text()),
        "avance": numero_visible(page.locator("#equipoAvance").inner_text()),
    }
    informe.verificar(
        "fila Equipo: líneas, importe, cajas y kilos son la suma de la API (solo vendedores con meta)",
        dom_equipo == esperado_equipo,
        {"pantalla": dom_equipo, "api": esperado_equipo},
    )

    # Filas por vendedor: líneas, estado y avance contra la API.
    filas_ok, filas_mal = 0, []
    for i in range(filas.count()):
        fila = filas.nth(i)
        vid = fila.get_attribute("data-vendedor-id")
        if not vid:
            continue
        vendedor = vendedor_en(datos, vendedor_id=vid)
        celdas = fila.evaluate(JS_CELDAS)
        avance_api = None
        if vendedor["cumplimiento"] is not None:
            avance_api = entero(Decimal(str(vendedor["cumplimiento"])) * 100)
        if (
            numero_visible(celdas[1]) == vendedor["cantidad_lineas"]
            and celdas[7] == vendedor["estado"]
            and numero_visible(celdas[4]) == avance_api
        ):
            filas_ok += 1
        else:
            filas_mal.append(
                {"vendedor": vendedor["nombre_visible"], "celdas": celdas,
                 "api": [vendedor["cantidad_lineas"], vendedor["estado"], avance_api]}
            )
    informe.verificar(
        f"filas por vendedor: líneas, avance y estado coinciden con la API ({filas_ok})",
        filas_ok > 0 and not filas_mal,
        filas_mal[:2],
    )

    # Expandir y contraer cada vendedor guardado; cajas y kilos sin «$» en la zona expandida.
    expandibles, fallas_exp, valores_medida = 0, [], []
    for i in range(filas.count()):
        fila = filas.nth(i)
        vid = fila.get_attribute("data-vendedor-id")
        boton = fila.locator("button[aria-expanded]")
        if not vid or not boton.count():
            continue
        vendedor = vendedor_en(datos, vendedor_id=vid)
        zona = ui.zona_de(fila)
        boton.click()
        page.wait_for_timeout(120)
        abierto = boton.get_attribute("aria-expanded") == "true" and zona.is_visible()
        visibles = zona.locator("form.oc-line").evaluate_all(
            "els => els.filter(e => e.offsetParent !== null).length"
        )
        valores_medida += zona.locator("form.oc-line").evaluate_all(
            "forms => forms.flatMap(f => [f.querySelector('[data-meta=cajas]').value, "
            "f.querySelector('[data-meta=kilos]').value])"
        )
        boton.click()
        page.wait_for_timeout(120)
        cerrado = boton.get_attribute("aria-expanded") == "false" and zona.is_hidden()
        expandibles += 1
        if not (abierto and visibles == vendedor["cantidad_lineas"] and cerrado):
            fallas_exp.append(
                {"vendedor": vendedor["nombre_visible"], "abierto": abierto, "visibles": visibles,
                 "api": vendedor["cantidad_lineas"], "cerrado": cerrado}
            )
    informe.verificar(
        f"expandir y contraer: aria-expanded y líneas visibles = cantidad_lineas ({expandibles} vendedores)",
        expandibles > 0 and not fallas_exp,
        fallas_exp[:2],
    )
    informe.verificar(
        "cajas y kilos sin «$» en las zonas expandidas",
        bool(valores_medida) and all("$" not in valor for valor in valores_medida),
        f"{len(valores_medida)} valores",
    )

    # Borrador de un vendedor sin líneas (CARLA): «Sin meta», meta y avance «—», realizado de la API.
    page.click("#agregarVendedor")
    abrir_control(page, ui.borrador_vendedor())
    page.keyboard.type(CARLA)
    opcion_vendedor = page.locator(".ts-dropdown:visible .option", has_text=CARLA).first
    expect(opcion_vendedor).to_be_visible(timeout=8000)
    opcion_vendedor.click()
    page.wait_for_timeout(300)
    borrador_carla = ui.borrador_vendedor(CARLA)
    ref_carla = borrador_carla.evaluate("e => e.dataset.vendedorRef || ''")
    celdas_b = borrador_carla.evaluate(JS_CELDAS)
    api_carla = vendedor_en(datos, nombre=CARLA)
    informe.verificar(
        "borrador de vendedor sin líneas: «Sin meta», meta y avance «—», realizado de la API",
        celdas_b[7] == "Sin meta"
        and celdas_b[2] == "—"
        and celdas_b[4] == "—"
        and numero_visible(celdas_b[3]) == entero(api_carla["realizados"]["importe"]),
        celdas_b,
    )

    # Guardar otra línea (PATCH de ANA) no cierra ni cambia el borrador abierto.
    ui.expandir(ANA)
    linea_ana = ui.linea(ANA)
    linea_ana.locator('[data-meta="importe"]').fill("1700000")
    respuesta = enviar_linea(page, linea_ana, "PATCH", "/api/objetivos-comerciales/")
    esperar_carga(page)
    page.wait_for_timeout(300)
    informe.verificar(
        "al guardar otra línea, el borrador abierto se conserva con su mismo vendedor",
        respuesta.status == 200
        and ui.borrador_vendedor().count() == 1
        and ui.borrador_vendedor().evaluate("e => e.dataset.vendedorRef || ''") == ref_carla,
        f"{respuesta.status} {ref_carla}",
    )

    # Convertir un objetivo histórico no cierra el borrador abierto (solo cambia lo convertido).
    if not page.locator("details.oc-legacy").evaluate("d => d.open"):
        page.locator("details.oc-legacy summary").click()
    legacy_filas = page.locator("#legacyGoals tbody tr[data-goal-id]")
    expect(legacy_filas.first).to_be_visible(timeout=8000)
    antes_legacy = legacy_filas.count()
    fila_legacy = legacy_filas.first
    form_legacy = fila_legacy.locator("form[data-convert-form]")
    if fila_legacy.locator("select[data-month-mes]").count():
        fila_legacy.locator("select[data-month-mes]").select_option(MES[5:7])
        fila_legacy.locator("select[data-month-anio]").select_option(MES[:4])
    abrir_control(page, form_legacy)
    page.keyboard.type(BRUNO)
    expect(page.locator(".ts-dropdown:visible .option", has_text=BRUNO).first).to_be_visible(timeout=8000)
    page.locator(".ts-dropdown:visible .option", has_text=BRUNO).first.click()
    form_legacy.locator("select[data-company]").select_option("CARNES")
    form_legacy.locator("select[data-measure]").select_option("importe")
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/api/objetivos-comerciales/convertir" in r.url,
        timeout=15000,
    ) as info:
        form_legacy.locator("button[type=submit]").click()
    esperar_carga(page)
    page.wait_for_timeout(600)
    informe.verificar(
        "convertir objetivo histórico: el borrador abierto se conserva y la fila sale de pendientes",
        info.value.status == 201
        and ui.borrador_vendedor(CARLA).count() == 1
        and legacy_filas.count() == antes_legacy - 1,
        f"{info.value.status} {antes_legacy}->{legacy_filas.count()}",
    )

    if con_equipo:
        # T-Elena: sin líneas, aparece solo como borrador de la sesión.
        page.click("#agregarVendedor")
        abrir_control(page, ui.borrador_vendedor())
        page.keyboard.type("T-Elena")
        opcion_vendedor = page.locator(".ts-dropdown:visible .option", has_text="T-Elena").first
        expect(opcion_vendedor).to_be_visible(timeout=8000)
        opcion_vendedor.click()
        page.wait_for_timeout(300)
        elena = ui.borrador_vendedor("T-Elena")
        celdas_e = elena.evaluate(JS_CELDAS)
        api_elena = vendedor_en(datos, nombre="T-Elena")
        realizado_elena = numero_visible(celdas_e[3])
        informe.verificar(
            "T-Elena en la sesión: «Sin meta» una sola vez, meta y avance «—», realizado de la API y distinto de 0",
            page.locator("[data-seller-row]", has_text="T-Elena").count() == 1
            and celdas_e[7] == "Sin meta"
            and celdas_e[2] == "—"
            and celdas_e[4] == "—"
            and realizado_elena == entero(api_elena["realizados"]["importe"])
            and realizado_elena != 0,
            celdas_e,
        )
        ui.zona_de(elena).locator("[data-cancel-draft]").click()
        page.wait_for_timeout(200)
        informe.verificar(
            "descartar el borrador de T-Elena la quita de la tabla",
            ui.borrador_vendedor("T-Elena").count() == 0,
        )

    # Escapes: un nombre con &, <, comillas simples se muestra como texto, sin markup inyectado.
    nombre_escape = "Vendedora & <i>'Q'"
    page.click("#agregarVendedor")
    abrir_control(page, ui.borrador_vendedor())
    page.keyboard.type(nombre_escape)
    page.wait_for_timeout(400)
    page.keyboard.press("Enter")
    page.wait_for_timeout(400)
    ui.zona_de(ui.borrador_vendedor()).locator("[data-add-line]").click()
    linea_escape = ui.formulario_alta()
    elegir_nivel(page, "marca")
    page.wait_for_timeout(300)
    abrir_control(page, ui.campo_alta("valor"))
    page.keyboard.type("Norte")
    expect(opcion(ui.campo_alta("valor"), "Marca Norte")).to_be_visible(timeout=8000)
    opcion(ui.campo_alta("valor"), "Marca Norte").click()
    page.wait_for_timeout(300)
    linea_escape.locator('[data-meta="importe"]').fill("50000")
    respuesta = enviar_linea(page, linea_escape, "POST", "/api/objetivos-comerciales")
    esperar_carga(page)
    page.wait_for_timeout(300)
    fila_escape = ui.filas_vendedor().filter(has_text=nombre_escape).first
    th_escape = fila_escape.locator("th")
    boton_escape = fila_escape.locator("button[aria-expanded]")
    zona_escape = ui.zona_de(fila_escape)
    informe.verificar(
        "nombre con &, <, comillas: se muestra como texto en la fila, el botón y la zona (sin markup inyectado)",
        respuesta.status == 201
        and th_escape.locator("i, b, img, script").count() == 0
        and nombre_escape in normalizar(th_escape.inner_text())
        and boton_escape.get_attribute("title") == nombre_escape
        and zona_escape.locator("td").first.get_attribute("aria-label") == f"Líneas de {nombre_escape}",
        f"{respuesta.status} {normalizar(th_escape.inner_text())}",
    )

    # Medidas: con las filas contraídas, la tabla entra en la pantalla sin scroll horizontal.
    medidas = []
    for ancho, alto in ((1366, 768), (1440, 900)):
        page.set_viewport_size({"width": ancho, "height": alto})
        page.goto(BASE_URL + "/comercial/objetivos", wait_until="domcontentloaded")
        esperar_carga(page)
        page.wait_for_timeout(300)
        medidas.append({"viewport": f"{ancho}x{alto}", **page.evaluate(JS_MEDIDAS)})
        tomar(page, carpeta, f"10-tabla-{ancho}x{alto}")
    # Criterio del brief: con 6 vendedores contraídos, la comparación entra sin scroll. Se mide la sexta fila
    # más la fila Equipo; el cuadro con todas las filas se informa aparte, sin ser criterio.
    informe.verificar(
        "medidas: con 6 vendedores contraídos, la comparación entra en 1366×768 y 1440×900 sin scroll horizontal, con cifras a la derecha",
        all(
            m["seis_contraidos_inferior"] <= m["alto"]
            and m["scroll_horizontal"] <= 0
            and m["numericas_derecha"]
            and m["contraidas"]
            for m in medidas
        ),
        medidas,
    )


# ---------------------------------------------------------------------------
# Panel lateral de alta (corte 3). Disparador con vendedor fijado, TomSelect dentro del panel,
# Guardar, Guardar y agregar otro, Cancelar, Escape, clic fuera, validación con texto, escapes del nombre
# y medidas. Los datos se leen del GET de objetivos; el DOM aporta foco, geometría y textos visibles.
# ---------------------------------------------------------------------------
MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
            "septiembre", "octubre", "noviembre", "diciembre"]
BORRADOR_CONSERVADO = "Vendedora Borrador Conservado"
NOMBRE_ESCAPES = "Vendedora Borrador & <i>'Q' \"R\""

JS_PANEL_MEDIDAS = """(vendedorId) => {
  const panel = document.querySelector('[data-goal-drawer]');
  const caja = panel.getBoundingClientRect();
  const grilla = panel.querySelector('.oc-goal-grid');
  const columnas = getComputedStyle(grilla).gridTemplateColumns.trim().split(/\\s+/).length;
  const arriba = sel => { const el = panel.querySelector(sel); return el ? el.getBoundingClientRect().top : NaN; };
  const fila = document.querySelector(`tr[data-seller-row][data-vendedor-id="${vendedorId}"]`);
  const derechas = fila ? [...fila.children].slice(0, 5).map(celda => celda.getBoundingClientRect().right) : [];
  return {
    x: Math.round(caja.x), ancho: Math.round(caja.width), alto: Math.round(caja.height),
    dentro: caja.x >= 0 && caja.right <= innerWidth && caja.y >= 0 && caja.bottom <= innerHeight,
    sin_scroll_horizontal: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    columnas: columnas,
    importe_debajo: arriba('label[for="objetivoImporte"]') > arriba('[data-campo="nivel"] label'),
    etiquetas_nivel_valor: Math.abs(arriba('[data-campo="nivel"] label') - arriba('[data-campo="valor"] label')) <= 1,
    etiquetas_cajas_kilos: Math.abs(arriba('label[for="objetivoCajas"]') - arriba('label[for="objetivoKilos"]')) <= 1,
    controles_nivel_valor: Math.abs(arriba('[data-campo="nivel"] .ts-control') - arriba('[data-campo="valor"] .ts-control')) <= 1,
    controles_cajas_kilos: Math.abs(arriba('[data-meta="cajas"]') - arriba('[data-meta="kilos"]')) <= 1,
    fila_visible: derechas.length === 5 && derechas.every(x => x <= caja.x + 0.5),
    fila_derechas: derechas.map(x => Math.round(x)),
  };
}"""


def etiqueta_periodo(mes):
    anio, _, numero = mes.partition("-")
    return f"{MESES_ES[int(numero) - 1]} {anio}"


def visible_en(locator, segundos=5):
    try:
        expect(locator).to_be_visible(timeout=segundos * 1000)
        return True
    except AssertionError:
        return False


def oculto_en(locator, segundos=5):
    try:
        expect(locator).to_be_hidden(timeout=segundos * 1000)
        return True
    except AssertionError:
        return False


def foco_en_campo(page, campo):
    """True si el foco está dentro del campo del panel indicado por data-campo («nivel» o «valor»)."""
    return page.evaluate(
        "nombre => { const a = document.activeElement;"
        " return !!(a && a.closest(`[data-goal-drawer] [data-campo=\"${nombre}\"]`)); }",
        campo,
    )


def enfocado(page, locator):
    return page.evaluate("el => document.activeElement === el", locator.element_handle())


def elegir_nivel(page, nivel):
    campo = ObjetivosDOM(page).campo_alta("nivel")
    abrir_control(page, campo)
    campo.locator(f'.ts-dropdown .option[data-value="{nivel}"]').click()
    page.wait_for_timeout(250)


def elegir_valor(page, consulta, texto):
    campo = ObjetivosDOM(page).campo_alta("valor")
    abrir_control(page, campo)
    page.keyboard.type(consulta)
    expect(opcion(campo, texto)).to_be_visible(timeout=8000)
    opcion(campo, texto).click()
    page.wait_for_timeout(250)


def posts_de_objetivos(informe):
    return sum(
        1
        for r in informe.respuestas
        if r["metodo"] == "POST" and r["ruta"].startswith("/api/objetivos-comerciales")
    )


def panel_limpio(page):
    ui = ObjetivosDOM(page)
    return (
        ui.campo_alta("nivel").locator(".ts-control .item").count() == 0
        and ui.campo_alta("valor").locator(".ts-control .item").count() == 0
        and all(
            page.locator(f'[data-goal-form] [data-meta="{medida}"]').input_value() == ""
            for medida in ("importe", "cajas", "kilos")
        )
    )


def esperar_confirmacion_y_responder(page, aceptar):
    """Modal de la app (#app360ConfirmModal): acepta o mantiene. Devuelve si el modal apareció."""
    if not visible_en(page.locator("#app360ConfirmAccept")):
        return False
    page.locator("#app360ConfirmAccept" if aceptar else "#app360ConfirmCancel").click()
    return True


def capturar_panel(page, carpeta, nombre):
    """Captura del viewport: el panel es fijo y en página completa aparece desplazado."""
    os.makedirs(carpeta, exist_ok=True)
    page.screenshot(path=os.path.join(carpeta, nombre + ".png"), full_page=False)


def recorrido_panel_alta(page, informe, carpeta, contexto):
    print("== Panel lateral de alta", flush=True)
    ui = ObjetivosDOM(page)
    panel = page.locator("[data-goal-drawer]")
    subtitulo = page.locator("[data-goal-subtitle]")
    campo_valor = ui.campo_alta("valor")
    esperado_sub = f"{ANA} · {etiqueta_periodo(MES)}"

    page.goto(f"{BASE_URL}/comercial/objetivos?mes={MES}", wait_until="domcontentloaded")
    esperar_carga(page)
    page.wait_for_timeout(300)
    ui.expandir(ANA)
    fila = ui.fila_vendedor(ANA)
    vid = fila.get_attribute("data-vendedor-id")
    disparador = ui.zona_de(fila).locator("[data-add-line]")

    # Disparador de una fila guardada: vendedor fijado, subtítulo y foco en Nivel.
    disparador.click()
    expect(panel).to_be_visible(timeout=5000)
    informe.verificar(
        "panel: abre desde la fila de Ana con el vendedor fijado (igual data-vendedor-id de la fila)",
        vid is not None and panel.get_attribute("data-vendedor-id") == vid,
        {"fila": vid, "panel": panel.get_attribute("data-vendedor-id")},
    )
    sub = normalizar(subtitulo.inner_text())
    informe.verificar("panel: subtítulo «<vendedor> · <mes año>»", sub == esperado_sub, sub)
    informe.verificar("panel: el foco llega a Nivel al abrir", foco_en_campo(page, "nivel"))

    # TomSelect dentro del panel: el desplegable de Valor queda contenido en el panel, filtra y selecciona.
    elegir_nivel(page, "producto")
    abrir_control(page, campo_valor)
    desplegable = campo_valor.locator(".ts-dropdown").first
    caja_panel = panel.bounding_box()
    caja_desplegable = desplegable.bounding_box()
    contenido = bool(caja_panel and caja_desplegable) and (
        caja_desplegable["x"] >= caja_panel["x"] - 1
        and caja_desplegable["x"] + caja_desplegable["width"] <= caja_panel["x"] + caja_panel["width"] + 1
    )
    informe.verificar("TomSelect de Valor: el desplegable queda contenido en el panel", contenido)
    with page.expect_response(
        lambda r: "/api/objetivos-comerciales/opciones" in r.url and "q=Sardo" in r.url, timeout=10000
    ) as info:
        page.keyboard.type("Sardo")
    api = [o.get("value") for o in info.value.json().get("opciones", [])]
    textos = esperar_filtro(desplegable, "Sardo")
    informe.verificar(
        "TomSelect de Valor: «Sardo» filtra y las opciones visibles coinciden con /opciones",
        bool(textos) and set(textos) <= set(api) and "Queso Sardo Demo 1kg" in textos,
        {"visibles": textos[:5], "en_api": len(api)},
    )
    opcion(campo_valor, "Queso Sardo Demo 1kg").click()
    page.wait_for_timeout(250)
    informe.verificar(
        "TomSelect de Valor: la opción elegida queda seleccionada",
        item_seleccionado(campo_valor) == "Queso Sardo Demo 1kg",
        item_seleccionado(campo_valor),
    )

    # Cancelar con datos sin guardar: pide confirmación; al descartar, el GET de objetivos no cambia.
    antes = leer_objetivos(contexto, BASE_URL, MES)
    page.locator("[data-goal-form] [data-cancel-line]").click()
    informe.verificar(
        "Cancelar con datos sin guardar: pide confirmación (modal de la app) y el panel sigue abierto",
        visible_en(page.locator("#app360ConfirmAccept")) and panel.is_visible(),
    )
    page.locator("#app360ConfirmAccept").click()
    informe.verificar("Cancelar: el panel se cierra al descartar", oculto_en(panel))
    despues = leer_objetivos(contexto, BASE_URL, MES)
    informe.verificar(
        "Cancelar: snapshot del GET antes = después (no se creó ni cambió ninguna línea)",
        json.dumps(antes["objetivos"], sort_keys=True) == json.dumps(despues["objetivos"], sort_keys=True),
    )
    informe.verificar("Cancelar: el foco vuelve al disparador «Agregar objetivo»", enfocado(page, disparador))

    # Escape con el panel sin datos: cierra y devuelve el foco al disparador.
    disparador.click()
    expect(panel).to_be_visible(timeout=5000)
    page.keyboard.press("Escape")
    informe.verificar("Escape con el panel sin datos: cierra", oculto_en(panel))
    informe.verificar("Escape: el foco vuelve al disparador", enfocado(page, disparador))

    # Escape con datos sin guardar: pide confirmación; «Seguir editando» conserva el panel.
    disparador.click()
    expect(panel).to_be_visible(timeout=5000)
    page.locator('[data-goal-form] [data-meta="importe"]').fill("1000")
    page.keyboard.press("Escape")
    pidio = esperar_confirmacion_y_responder(page, aceptar=False)
    informe.verificar(
        "Escape con datos sin guardar: pide confirmación y «Seguir editando» conserva el panel",
        pidio and panel.is_visible(),
    )

    # Clic fuera con datos sin guardar: pide confirmación; «Descartar» cierra.
    page.locator("h1").first.click()
    pidio = esperar_confirmacion_y_responder(page, aceptar=True)
    informe.verificar(
        "clic fuera con datos sin guardar: pide confirmación y «Descartar» cierra el panel",
        pidio and oculto_en(panel),
    )

    # Validación con texto y sin envío: Valor sin elegir.
    disparador.click()
    expect(panel).to_be_visible(timeout=5000)
    elegir_nivel(page, "rubro")
    page.locator('[data-goal-form] [data-meta="importe"]').fill("50000")
    posts_antes = posts_de_objetivos(informe)
    page.locator('[data-goal-form] button[type="submit"]').click()
    aviso = page.locator("[data-goal-form] [data-line-error]")
    mostrado = visible_en(aviso)
    texto_aviso = normalizar(aviso.inner_text()) if mostrado else ""
    informe.verificar(
        "validación: sin Valor elegido, el aviso aparece en texto y no se envía nada",
        mostrado and "valor" in texto_aviso.lower() and posts_de_objetivos(informe) == posts_antes,
        texto_aviso,
    )
    capturar_panel(page, carpeta, "panel-validacion-sin-valor")
    page.keyboard.press("Escape")
    esperar_confirmacion_y_responder(page, aceptar=True)
    informe.verificar("validación: el panel se cierra al descartar", oculto_en(panel))

    # Guardar y agregar otro: POST 201 + readback; el panel queda abierto, limpio, con foco en Nivel.
    disparador.click()
    expect(panel).to_be_visible(timeout=5000)
    elegir_nivel(page, "rubro")
    elegir_valor(page, "teos", "Lácteos")
    page.locator('[data-goal-form] [data-meta="importe"]').fill("100000")
    lineas_antes = cantidad_lineas(leer_objetivos(contexto, BASE_URL, MES), vendedor_id=vid)
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/api/objetivos-comerciales" in r.url and "/convertir" not in r.url,
        timeout=15000,
    ) as info:
        page.locator("[data-goal-form] [data-save-and-add]").click()
    respuesta = info.value
    informe.verificar("Guardar y agregar otro responde 201", respuesta.status == 201, respuesta.status)
    esperar_carga(page)
    page.wait_for_timeout(300)
    datos = leer_objetivos(contexto, BASE_URL, MES)
    ok, detalle = comparar_linea_readback(
        datos,
        objetivo_devuelto(respuesta).get("id"),
        {"importe": 100000, "cajas": 0, "kilos": 0},
        lineas_antes + 1,
        vendedor_id=vid,
    )
    informe.verificar("Guardar y agregar otro: readback de la API confirma id, metas y cantidad de líneas", ok, detalle)
    informe.verificar(
        "Guardar y agregar otro: el panel queda abierto con el mismo vendedor",
        panel.is_visible()
        and panel.get_attribute("data-vendedor-id") == vid
        and normalizar(subtitulo.inner_text()) == esperado_sub,
    )
    informe.verificar("Guardar y agregar otro: formulario limpio (Nivel, Valor e importe vacíos)", panel_limpio(page))
    informe.verificar("Guardar y agregar otro: el foco queda en Nivel", foco_en_campo(page, "nivel"))
    celdas = fila.evaluate(JS_CELDAS)
    informe.verificar(
        "fila de Ana detrás del panel: cantidad de líneas = la de la API",
        numero_visible(celdas[1]) == lineas_antes + 1,
        celdas[1],
    )

    # Error del servidor dentro del panel: un duplicado exacto (mismo vendedor, mes, nivel y valor) responde 409.
    elegir_nivel(page, "rubro")
    elegir_valor(page, "teos", "Lácteos")
    page.locator('[data-goal-form] [data-meta="importe"]').fill("50000")
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/api/objetivos-comerciales" in r.url and "/convertir" not in r.url,
        timeout=15000,
    ) as info:
        page.locator('[data-goal-form] button[type="submit"]').click()
    aviso_servidor = page.locator("[data-goal-form] [data-line-error]")
    mostrado = visible_en(aviso_servidor)
    texto_servidor = normalizar(aviso_servidor.inner_text()) if mostrado else ""
    informe.verificar(
        "error del servidor (duplicado, 409): el mensaje de la API aparece dentro del panel y el panel sigue abierto",
        info.value.status == 409 and mostrado and bool(texto_servidor) and panel.is_visible(),
        f"{info.value.status} {texto_servidor[:90]}",
    )

    # Guardar: POST 201 + readback; el panel se cierra y el foco vuelve al disparador.
    elegir_nivel(page, "marca")
    elegir_valor(page, "Norte", "Marca Norte")
    page.locator('[data-goal-form] [data-meta="importe"]').fill("90000")
    lineas_antes = cantidad_lineas(leer_objetivos(contexto, BASE_URL, MES), vendedor_id=vid)
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/api/objetivos-comerciales" in r.url and "/convertir" not in r.url,
        timeout=15000,
    ) as info:
        page.locator('[data-goal-form] button[type="submit"]').click()
    respuesta = info.value
    informe.verificar("Guardar responde 201", respuesta.status == 201, respuesta.status)
    esperar_carga(page)
    page.wait_for_timeout(300)
    datos = leer_objetivos(contexto, BASE_URL, MES)
    ok, detalle = comparar_linea_readback(
        datos,
        objetivo_devuelto(respuesta).get("id"),
        {"importe": 90000, "cajas": 0, "kilos": 0},
        lineas_antes + 1,
        vendedor_id=vid,
    )
    informe.verificar("Guardar: readback de la API confirma id, metas y cantidad de líneas", ok, detalle)
    informe.verificar("Guardar: el panel se cierra", oculto_en(panel))
    informe.verificar("Guardar: el foco vuelve al disparador «Agregar objetivo»", enfocado(page, disparador))
    celdas = fila.evaluate(JS_CELDAS)
    informe.verificar(
        "Guardar: la fila de Ana muestra la cantidad de líneas de la API",
        numero_visible(celdas[1]) == lineas_antes + 1,
        celdas[1],
    )

    # Borrador de otro vendedor: al guardar una línea de Ana, el borrador abierto conserva su vendedor.
    page.click("#agregarVendedor")
    abrir_control(page, ui.borrador_vendedor())
    page.keyboard.type(BORRADOR_CONSERVADO)
    page.wait_for_timeout(400)
    page.keyboard.press("Enter")
    page.wait_for_timeout(400)
    ref_borrador = ui.borrador_vendedor(BORRADOR_CONSERVADO).evaluate("e => e.dataset.vendedorRef || ''")
    disparador.click()
    expect(panel).to_be_visible(timeout=5000)
    elegir_nivel(page, "marca")
    elegir_valor(page, "Frigo", "Frigo Demo")
    page.locator('[data-goal-form] [data-meta="importe"]').fill("70000")
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/api/objetivos-comerciales" in r.url and "/convertir" not in r.url,
        timeout=15000,
    ) as info:
        page.locator('[data-goal-form] button[type="submit"]').click()
    informe.verificar("alta de Ana con un borrador abierto: responde 201", info.value.status == 201, info.value.status)
    esperar_carga(page)
    page.wait_for_timeout(300)
    borrador = ui.borrador_vendedor(BORRADOR_CONSERVADO)
    informe.verificar(
        "borrador de otro vendedor conservado con su mismo vendedor tras guardar en Ana",
        ref_borrador.startswith("nombre:")
        and borrador.count() == 1
        and borrador.evaluate("e => e.dataset.vendedorRef || ''") == ref_borrador,
        ref_borrador,
    )

    # Nombre con &, <, comillas simples y dobles: el subtítulo y el panel lo muestran como texto.
    page.click("#agregarVendedor")
    abrir_control(page, ui.borrador_vendedor())
    page.keyboard.type(NOMBRE_ESCAPES)
    page.wait_for_timeout(400)
    page.keyboard.press("Enter")
    page.wait_for_timeout(400)
    ui.zona_de(ui.borrador_vendedor(NOMBRE_ESCAPES)).locator("[data-add-line]").click()
    expect(panel).to_be_visible(timeout=5000)
    texto_sub = subtitulo.inner_text()
    informe.verificar(
        "nombre con &, <, comillas simples y dobles: el subtítulo muestra el texto literal, sin markup",
        normalizar(texto_sub).startswith(NOMBRE_ESCAPES)
        and subtitulo.locator("i, b, img, script").count() == 0
        and panel.get_attribute("data-vendedor-ref") == f"nombre:{NOMBRE_ESCAPES}",
        texto_sub,
    )
    page.keyboard.press("Escape")
    informe.verificar("cierre con Escape tras el chequeo de escapes", oculto_en(panel))

    # Medidas: 1440×900 y 1366×768. Cada viewport guarda una línea sintética de Ana con «Guardar y agregar otro».
    medidas = []
    for ancho, alto, marca, consulta in ((1440, 900, "Sierra Demo", "Sierra"), (1366, 768, "Estancia Sur", "Estancia")):
        page.set_viewport_size({"width": ancho, "height": alto})
        page.goto(f"{BASE_URL}/comercial/objetivos?mes={MES}", wait_until="domcontentloaded")
        esperar_carga(page)
        page.wait_for_timeout(300)
        ui.expandir(ANA)
        fila_v = ui.fila_vendedor(ANA)
        disparador_v = ui.zona_de(fila_v).locator("[data-add-line]")
        cabecera = page.locator("#agregarVendedor")
        color_cerrado = cabecera.evaluate("el => getComputedStyle(el).backgroundColor")
        disparador_v.click()
        expect(panel).to_be_visible(timeout=5000)
        capturar_panel(page, carpeta, f"panel-vacio-{ancho}x{alto}")
        elegir_nivel(page, "marca")
        medida = page.evaluate(JS_PANEL_MEDIDAS, vid)
        medida["viewport"] = f"{ancho}x{alto}"
        medida["cabecera_cerrada"] = color_cerrado
        medida["cabecera_abierta"] = cabecera.evaluate("el => getComputedStyle(el).backgroundColor")
        abrir_control(page, campo_valor)
        page.keyboard.type(consulta)
        expect(opcion(campo_valor, marca)).to_be_visible(timeout=8000)
        capturar_panel(page, carpeta, f"valor-abierto-{ancho}x{alto}")
        opcion(campo_valor, marca).click()
        page.wait_for_timeout(250)
        page.locator('[data-goal-form] [data-meta="importe"]').fill("")
        page.locator('[data-goal-form] button[type="submit"]').click()
        visible_en(page.locator("[data-goal-form] [data-line-error]"))
        medida["error_visible"] = normalizar(page.locator("[data-goal-form] [data-line-error]").inner_text())
        capturar_panel(page, carpeta, f"panel-error-{ancho}x{alto}")
        page.locator('[data-goal-form] [data-meta="importe"]').fill("60000")
        with page.expect_response(
            lambda r: r.request.method == "POST" and "/api/objetivos-comerciales" in r.url and "/convertir" not in r.url,
            timeout=15000,
        ) as info:
            page.locator("[data-goal-form] [data-save-and-add]").click()
        medida["post"] = info.value.status
        esperar_carga(page)
        page.wait_for_timeout(300)
        capturar_panel(page, carpeta, f"tras-guardar-y-agregar-otro-{ancho}x{alto}")
        page.keyboard.press("Escape")
        medidas.append(medida)
        page.goto(f"{BASE_URL}/comercial/objetivos?mes={MES}", wait_until="domcontentloaded")
        esperar_carga(page)

    informe.verificar(
        "medidas: el panel queda dentro del viewport y sin scroll horizontal (1440×900 y 1366×768)",
        all(m["dentro"] and m["sin_scroll_horizontal"] for m in medidas),
        [(m["viewport"], m["dentro"], m["sin_scroll_horizontal"]) for m in medidas],
    )
    informe.verificar(
        "medidas: grilla de dos columnas; Importe a fila completa debajo de Nivel y Valor",
        all(m["columnas"] == 2 and m["importe_debajo"] for m in medidas),
        [(m["viewport"], m["columnas"], m["importe_debajo"]) for m in medidas],
    )
    informe.verificar(
        "medidas: etiquetas y controles de cada fila a la misma altura (≤ 1 px)",
        all(
            m["etiquetas_nivel_valor"] and m["etiquetas_cajas_kilos"]
            and m["controles_nivel_valor"] and m["controles_cajas_kilos"]
            for m in medidas
        ),
        [(m["viewport"], m["etiquetas_nivel_valor"], m["etiquetas_cajas_kilos"]) for m in medidas],
    )
    informe.verificar(
        "medidas: con el panel abierto, «Agregar vendedor» pasa a secundaria",
        all(m["cabecera_abierta"] != m["cabecera_cerrada"] for m in medidas),
        [(m["cabecera_cerrada"], m["cabecera_abierta"]) for m in medidas],
    )
    informe.verificar(
        "medidas: la fila del vendedor activo (Vendedor, Líneas, Meta, Realizado, Avance) queda visible junto al panel",
        all(m["fila_visible"] for m in medidas),
        [(m["viewport"], m["fila_derechas"], m["x"]) for m in medidas],
    )
    informe.verificar(
        "medidas: «Guardar y agregar otro» responde 201 en ambos viewports",
        all(m["post"] == 201 for m in medidas),
        [(m["viewport"], m["post"]) for m in medidas],
    )
    informe.verificar(
        "validación: el aviso de meta en el panel se ve en ambos viewports",
        all("meta mayor que cero" in m["error_visible"] for m in medidas),
        [(m["viewport"], m["error_visible"][:60]) for m in medidas],
    )


def sembrar_si_corresponde(sin_reset):
    if not sin_reset:
        subprocess.run([RUN_LOCAL, "reset"], check=True, stdout=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--sin-reset", action="store_true", help="no reinicia los datos sintéticos")
    args = parser.parse_args()
    if not (BASE_URL.startswith("http://127.0.0.1:") or BASE_URL.startswith("http://localhost:")):
        raise SystemExit("El E2E solo corre contra la app local (127.0.0.1 o localhost).")

    sembrar_si_corresponde(args.sin_reset)
    informe = Informe()
    os.makedirs(SHOTS_DIR, exist_ok=True)
    with sync_playwright() as p:
        lanzar = {"headless": True, "args": ["--no-sandbox"]}
        port = urlparse(BASE_URL).port
        if port:
            lanzar["args"].append(f"--explicitly-allowed-ports={port}")
        if os.path.exists(CHROMIUM):
            lanzar["executable_path"] = CHROMIUM
        navegador = p.chromium.launch(**lanzar)
        try:
            recorrido_permisos(navegador, informe)
            contexto = navegador.new_context(viewport={"width": 1400, "height": 1000})
            page = contexto.new_page()
            instrumentar(page, informe)
            ingreso = login(page, ADMIN_USER, ADMIN_PASSWORD)
            informe.verificar("login admin por formulario", ingreso, urlparse(page.url).path)
            if ingreso:
                recorrido_admin(page, informe, SHOTS_DIR, contexto)
                recorrido_tabla_equipo(page, informe, SHOTS_DIR, contexto)
                recorrido_panel_alta(page, informe, SHOTS_DIR, contexto)
            contexto.close()
        finally:
            navegador.close()

    total, fallas = informe.guardar(os.path.join(SHOTS_DIR, "informe.json"))
    print(
        f"\nRESUMEN: {total - fallas}/{total} verificaciones OK. Informe: {SHOTS_DIR}/informe.json"
    )
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
