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
from urllib.parse import urlparse

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


def card_vendedor(page, nombre):
    return (
        page.locator("article.oc-seller-card").filter(has=page.locator("h2", has_text=nombre)).first
    )


def borrador(page):
    return page.locator("article.oc-seller-draft").first


def tarjeta_activa(page, nombre):
    """Borrador si el vendedor todavía no tiene líneas guardadas; si no, su tarjeta guardada."""
    if borrador(page).count():
        return borrador(page)
    return card_vendedor(page, nombre)


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


def recorrido_admin(page, informe, carpeta):
    print("== Pantalla de objetivos (admin)", flush=True)
    page.goto(BASE_URL + "/comercial/objetivos", wait_until="domcontentloaded")
    esperar_carga(page)
    page.locator("#periodoMes").select_option(MES[5:7])
    page.locator("#periodoAnio").select_option(MES[:4])
    page.dispatch_event("#periodoObjetivos", "change")
    esperar_carga(page)
    page.wait_for_timeout(400)
    tomar(page, carpeta, "01-pagina")
    tarjetas = page.locator("article.oc-seller-card").count()
    informe.verificar("la pantalla carga las tarjetas del período", tarjetas >= 3, tarjetas)

    # Alta de vendedor desde el catálogo.
    page.click("#agregarVendedor")
    abrir_control(page, borrador(page))
    page.keyboard.type(DIEGO)
    opcion_diego = page.locator(".ts-dropdown:visible .option", has_text=DIEGO).first
    expect(opcion_diego).to_be_visible(timeout=8000)
    opcion_diego.click()
    page.wait_for_timeout(300)
    referencia = borrador(page).evaluate("e => e.dataset.vendedorRef || ''")
    informe.verificar(
        "alta de vendedor desde el catálogo", referencia.startswith("id:"), referencia
    )

    # Cada nivel: abrir sin escribir, buscar, elegir, guardar.
    for caso in NIVELES:
        nivel = caso["nivel"]
        print(f"-- nivel {nivel}", flush=True)
        tarjeta = tarjeta_activa(page, DIEGO)
        tarjeta.locator("[data-add-line]").click()
        linea = tarjeta_activa(page, DIEGO).locator("form.oc-line").last
        linea.locator("select[data-dimension-tipo]").select_option(nivel)
        page.wait_for_timeout(300)
        abrir_control(page, linea)
        dropdown = linea.locator(".ts-dropdown").first
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
        seleccion = item_seleccionado(linea)
        informe.verificar(
            f"[{nivel}] la selección queda elegida", seleccion == caso["esperada"], seleccion
        )
        tomar(page, carpeta, f"03-{nivel}-elegido")

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
            abrir_control(page, linea)
            page.keyboard.type("Ricota")
            expect(opcion(linea, "Ricota")).to_be_visible(timeout=8000)
            opcion(linea, "Ricota").click()
            page.wait_for_timeout(300)
            informe.verificar(
                "producto sin cantidades: cajas y kilos deshabilitados",
                linea.locator('[data-meta="cajas"]').is_disabled()
                and linea.locator('[data-meta="kilos"]').is_disabled(),
                item_seleccionado(linea),
            )
            abrir_control(page, linea)
            page.keyboard.type(caso["consulta"])
            expect(opcion(linea, caso["esperada"])).to_be_visible(timeout=8000)
            opcion(linea, caso["esperada"]).click()
            page.wait_for_timeout(300)
            linea.locator('[data-meta="cajas"]').fill("10")
            linea.locator('[data-meta="kilos"]').fill("20")

        linea.locator('[data-meta="importe"]').fill(caso["importe"])
        respuesta = enviar_linea(page, linea, "POST", "/api/objetivos-comerciales")
        informe.verificar(
            f"[{nivel}] guardar la línea responde 201",
            respuesta.status == 201,
            f"{respuesta.status} {respuesta.text()[:150]}",
        )
        esperar_carga(page)
        page.wait_for_timeout(300)
        visibles = (
            card_vendedor(page, DIEGO)
            .locator("form.oc-line")
            .filter(has_text=caso["esperada"])
            .count()
        )
        informe.verificar(
            f"[{nivel}] la línea guardada aparece en la tarjeta", visibles >= 1, visibles
        )
        tomar(page, carpeta, f"05-{nivel}-guardado")

    # Edición de una línea existente (Ana).
    print("-- editar y eliminar líneas", flush=True)
    linea_ana = card_vendedor(page, ANA).locator("form.oc-line").first
    linea_ana.locator('[data-meta="importe"]').fill("1600000")
    respuesta = enviar_linea(page, linea_ana, "PATCH", "/api/objetivos-comerciales/")
    informe.verificar(
        "editar línea existente responde 200",
        respuesta.status == 200,
        f"{respuesta.status} {respuesta.text()[:150]}",
    )
    esperar_carga(page)
    page.wait_for_timeout(300)
    resumen = normalizar(card_vendedor(page, ANA).locator("[data-summary]").inner_text())
    informe.verificar(
        "la edición queda reflejada en el resumen del vendedor",
        "1.600.000" in resumen,
        resumen[:160],
    )
    tomar(page, carpeta, "06-editar-linea")

    # Eliminación de una línea existente (Carla).
    carla = card_vendedor(page, CARLA)
    antes = carla.locator("form.oc-line").count()
    carla.locator("form.oc-line").first.locator("[data-delete-line]").click()
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
    despues = card_vendedor(page, CARLA).locator("form.oc-line").count()
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
    abrir_control(page, borrador(page))
    page.keyboard.type(NUEVA)
    page.wait_for_timeout(400)
    page.keyboard.press("Enter")
    page.wait_for_timeout(400)
    referencia = borrador(page).evaluate("e => e.dataset.vendedorRef || ''")
    informe.verificar(
        "vendedor nuevo queda seleccionado por nombre", referencia == f"nombre:{NUEVA}", referencia
    )
    borrador(page).locator("[data-add-line]").click()
    linea_nueva = borrador(page).locator("form.oc-line").last
    linea_nueva.locator("select[data-dimension-tipo]").select_option("marca")
    page.wait_for_timeout(300)
    abrir_control(page, linea_nueva)
    page.keyboard.type("Campo")
    expect(opcion(linea_nueva, "Campo Demo")).to_be_visible(timeout=8000)
    opcion(linea_nueva, "Campo Demo").click()
    page.wait_for_timeout(300)
    linea_nueva.locator('[data-meta="importe"]').fill("80000")
    respuesta = enviar_linea(page, linea_nueva, "POST", "/api/objetivos-comerciales")
    informe.verificar(
        "alta con vendedor nuevo responde 201",
        respuesta.status == 201,
        f"{respuesta.status} {respuesta.text()[:140]}",
    )
    esperar_carga(page)
    page.wait_for_timeout(300)
    informe.verificar(
        "el vendedor nuevo aparece como tarjeta", card_vendedor(page, NUEVA).count() == 1
    )
    tomar(page, carpeta, "09-vendedor-nuevo")
    informe.verificar(
        "la pantalla termina sin error de carga", page.locator("#objetivosError").is_hidden()
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
                recorrido_admin(page, informe, SHOTS_DIR)
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
