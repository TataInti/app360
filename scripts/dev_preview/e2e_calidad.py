"""Recorrido E2E de calidad básica de pantallas de App360 (cortes C1 a C9).

Requiere el entorno local levantado con `scripts/dev_preview/run_local.sh up` y la
app en 127.0.0.1:5055 apuntando a este worktree. Entra por el formulario de login real
con usuarios sintéticos (seed_demo.py). Por defecto reinicia los datos sintéticos
(`run_local.sh reset`); usá --sin-reset para conservar el estado actual.

Capturas e informe JSON en CAPTURAS/<etiqueta>/ (fuera del repo). Código de salida:
0 solo si todas las verificaciones pasan; 1 si alguna falla.

Uso:
    scripts/dev_preview/run_local.sh up
    /root/.cache/app360-e2e-venv/bin/python scripts/dev_preview/e2e_calidad.py --etiqueta despues
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RUN_LOCAL = os.environ.get("E2E_RUN_LOCAL") or os.path.join(ROOT_DIR, "scripts", "dev_preview", "run_local.sh")
LOCK = "/root/.hermes/cache/scratch/heavy.lock"
BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5055").rstrip("/")
ADMIN_USER = os.environ.get("E2E_ADMIN_USER", "admin")
# Clave de prueba SOLO-DEV del entorno E2E local (run_local.sh); no es una credencial real.
ADMIN_PASSWORD = os.environ.get("E2E_ADMIN_PASSWORD", "e2e-admin-ficticio")
CLAVE_VENTAS = os.environ.get("E2E_CLAVE_VENTAS", "e2e-ventas-ficticia")
CHROMIUM = os.environ.get(
    "E2E_CHROMIUM", "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
)
AXE_JS = os.environ.get(
    "E2E_AXE_JS",
    "/root/.cache/analiticastudio-shared/d84f3ace7744/node_modules/axe-core/axe.min.js",
)
CAPTURAS = os.environ.get("E2E_CAPTURAS", "/root/.hermes/cache/scratch/calidad-shots")
ZONA = timezone(timedelta(hours=-3))
AHORA = datetime.now(ZONA)
MES = AHORA.strftime("%Y-%m")
HOY = AHORA.strftime("%Y-%m-%d")

# Vendedor sintético de la semilla y línea que se usa para probar el duplicado (C1).
DIEGO = "Vendedor Demo Diego"
EMPRESA = "LACTEOS"
MENSAJE_DUPLICADO = (
    "Ya existe una línea de empresa «LACTEOS» para ese mes. "
    "Editala en lugar de crear otra."
)
MENSAJE_SESION = "Tu sesión terminó o no tenés acceso a esta sección"
MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]
RUTA_COBERTURA_ACCESIBILIDAD = [
    ("Ventas", "/dashboard-comercial"),
    ("Objetivos", "/comercial/objetivos"),
    ("Salón", "/comercial/salon"),
    ("Seguimiento", "/comercial/seguimiento-clientes"),
    ("Performance", "/comercial/performance-vendedores"),
    ("Criterio", "/ventas/criterio-clientes"),
]


class Informe:
    def __init__(self):
        self.verificaciones = []

    def verificar(self, nombre, ok, detalle=""):
        ok = bool(ok)
        self.verificaciones.append({"nombre": nombre, "ok": ok, "detalle": str(detalle)[:500]})
        sufijo = f" -- {str(detalle)[:220]}" if detalle != "" else ""
        print(f"{'OK   ' if ok else 'FALLA'} {nombre}{sufijo}", flush=True)
        return ok

    def guardar(self, ruta, extra=None):
        fallas = [v for v in self.verificaciones if not v["ok"]]
        salida = {
            "base_url": BASE_URL,
            "mes": MES,
            "total": len(self.verificaciones),
            "fallas": len(fallas),
            "verificaciones": self.verificaciones,
        }
        if extra:
            salida.update(extra)
        with open(ruta, "w", encoding="utf-8") as fh:
            json.dump(salida, fh, ensure_ascii=False, indent=2)
        return len(self.verificaciones), len(fallas)


class Monitor:
    """Registra consola, excepciones y respuestas 4xx/5xx de una página."""

    def __init__(self, page):
        self.errores_consola = []
        self.excepciones = []
        self.respuestas = []
        self.navegaciones = []
        self.pagina = page
        page.on("console", self._consola)
        page.on("pageerror", lambda e: self.excepciones.append(str(e)[:200]))
        page.on("response", self._respuesta)
        # Se registran las peticiones de navegación: un redirect del servidor no cambia la
        # ruta que reporta framenavigated, pero sí aparece como petición a la pantalla origen.
        page.on(
            "request",
            lambda req: self.navegaciones.append(urlparse(req.url).path)
            if req.is_navigation_request() and req.frame == page.main_frame
            else None,
        )

    def _consola(self, mensaje):
        if mensaje.type == "error":
            self.errores_consola.append(mensaje.text[:200])

    def _respuesta(self, respuesta):
        if respuesta.status >= 400:
            ruta = urlparse(respuesta.url)
            query = f"?{ruta.query}" if ruta.query else ""
            self.respuestas.append((respuesta.status, respuesta.request.method, ruta.path + query))

    def reiniciar(self):
        self.errores_consola.clear()
        self.excepciones.clear()
        self.respuestas.clear()
        self.navegaciones.clear()

    def inesperados(self, ignorar=()):
        """Respuestas 4xx/5xx no esperadas, errores de consola y excepciones.

        ignorar: pares (estado, fragmento de ruta) que son esperados por el caso.
        Cada respuesta 4xx/5xx genera un «Failed to load resource» en consola; los que
        sobran sin respuesta registrada se reportan aparte.
        """
        pendientes = []
        for estado, metodo, ruta in self.respuestas:
            if not any(estado == e and fragmento in ruta for e, fragmento in ignorar):
                pendientes.append(f"{metodo} {ruta} -> {estado}")
        ruido = [t for t in self.errores_consola if t.startswith("Failed to load resource")]
        otros = [t for t in self.errores_consola if not t.startswith("Failed to load resource")]
        sobrantes = len(ruido) - len(self.respuestas)
        if sobrantes > 0:
            pendientes.append(f"consola: {sobrantes} recurso(s) fallido(s) sin respuesta registrada")
        pendientes += [f"consola: {t}" for t in otros]
        pendientes += [f"excepción: {t}" for t in self.excepciones]
        return pendientes


def normalizar(texto):
    return " ".join((texto or "").split())


def esperar_pagina(page, ms=600):
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    page.wait_for_timeout(ms)


def ir(page, mon, ruta, ms=600):
    mon.reiniciar()
    page.goto(BASE_URL + ruta, wait_until="load")
    esperar_pagina(page, ms)


def esperar_js(page, expresion, segundos=20):
    """Sondea una expresión JS hasta que sea verdadera (evita wait_for_function por CSP)."""
    limite = time.time() + segundos
    while time.time() < limite:
        try:
            if page.evaluate(expresion):
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def foto(page, carpeta, nombre, completa=True):
    os.makedirs(carpeta, exist_ok=True)
    page.screenshot(path=os.path.join(carpeta, nombre + ".png"), full_page=completa)


def login(page, usuario, clave):
    page.goto(BASE_URL + "/", wait_until="domcontentloaded")
    page.fill("#username", usuario)
    page.fill("#password", clave)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")
    return urlparse(page.url).path != "/"


def ejecutar(nombre, informe, funcion, *args):
    """Corre un escenario; una excepción queda como falla y no corta los demás."""
    print(f"== {nombre}", flush=True)
    try:
        funcion(*args)
    except Exception as exc:  # noqa: BLE001 - el recorrido informa y sigue
        informe.verificar(f"{nombre}: el recorrido termina", False, f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Objetivos: C1 (duplicado), C5 (?mes=), C6 (selectores de mes en español)
# ---------------------------------------------------------------------------
def card_vendedor(page, nombre):
    """Fila de resumen del vendedor guardado; sus líneas están en la fila que sigue (tabla de equipo)."""
    return page.locator("[data-seller-row]:not([data-seller-draft])").filter(has_text=nombre).first


def borrador(page):
    return page.locator("[data-seller-draft]").first


def zona_de(fila):
    """Zona expandible de una fila de resumen: «Agregar objetivo» y los formularios de línea."""
    return fila.locator("xpath=following-sibling::tr[1]")


def tarjeta_activa(page, nombre):
    if borrador(page).count():
        return zona_de(borrador(page))
    return zona_de(card_vendedor(page, nombre))


def esperar_carga(page):
    page.wait_for_selector("#objetivosCarga[hidden]", state="attached", timeout=20000)


def campo_busqueda(contenedor):
    return contenedor.locator("input.dropdown-input").first


def abrir_control(page, contenedor):
    dropdown = contenedor.locator(".ts-dropdown").first
    if dropdown.is_visible():
        campo_busqueda(contenedor).click()
    else:
        contenedor.locator(".ts-control").first.click()
    expect(campo_busqueda(contenedor)).to_be_focused(timeout=5000)


def esperar_filtro(dropdown, consulta, segundos=5):
    limite = time.time() + segundos
    textos = []
    while time.time() < limite:
        textos = [normalizar(t) for t in dropdown.locator(".option").all_inner_texts() if t.strip()]
        if textos and all(consulta.lower() in t.lower() for t in textos):
            break
        time.sleep(0.15)
    return textos


def asegurar_tarjeta(page, nombre):
    if card_vendedor(page, nombre).count():
        return card_vendedor(page, nombre)
    if not borrador(page).count():
        page.click("#agregarVendedor")
    abrir_control(page, borrador(page))
    page.keyboard.type(nombre)
    opcion = page.locator(".ts-dropdown:visible .option", has_text=nombre).first
    expect(opcion).to_be_visible(timeout=8000)
    opcion.click()
    page.wait_for_timeout(300)
    return borrador(page)


def nueva_linea(page, nombre, nivel, consulta, esperada, importe):
    asegurar_tarjeta(page, nombre)
    tarjeta_activa(page, nombre).locator("[data-add-line]").click()
    linea = page.locator("[data-goal-form]")
    campo_nivel = linea.locator('[data-campo="nivel"]')
    abrir_control(page, campo_nivel)
    campo_nivel.locator(f'.ts-dropdown .option[data-value="{nivel}"]').click()
    page.wait_for_timeout(300)
    campo_valor = linea.locator('[data-campo="valor"]')
    abrir_control(page, campo_valor)
    dropdown = campo_valor.locator(".ts-dropdown").first
    page.keyboard.type(consulta)
    esperar_filtro(dropdown, consulta)
    dropdown.locator(".option", has_text=esperada).first.click()
    page.wait_for_timeout(300)
    linea.locator('input[data-meta="importe"]').fill(importe)
    return linea


def enviar_linea(page, linea, metodo, patron):
    with page.expect_response(
        lambda r: r.request.method == metodo and patron in r.url, timeout=15000
    ) as info:
        linea.locator("button[type=submit]").click()
    return info.value


def lineas_api(api, mes, nombre):
    """api: APIRequestContext (ctx.request) con la sesión del navegador."""
    respuesta = api.get(f"{BASE_URL}/api/objetivos-comerciales?mes={mes}&medida=importe")
    datos = respuesta.json()
    for vendedor in datos.get("objetivos", []):
        if vendedor.get("nombre_visible") == nombre:
            return vendedor.get("lineas", [])
    return []


def escenario_objetivos(navegador, informe, carpeta):
    ctx = navegador.new_context(locale="es-AR", viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    mon = Monitor(page)
    informe.verificar("login admin por formulario", login(page, ADMIN_USER, ADMIN_PASSWORD))

    # C5 y C6: el período viaja en la URL y se elige con selectores en español.
    ir(page, mon, "/comercial/objetivos?mes=2026-03")
    esperar_carga(page)
    valor_periodo = page.evaluate("() => document.getElementById('periodoObjetivos')?.value || ''")
    informe.verificar(
        "C5 Objetivos: ?mes=2026-03 carga el período desde la URL",
        valor_periodo == "2026-03",
        valor_periodo,
    )
    mes_select = page.locator("#periodoMes")
    anio_select = page.locator("#periodoAnio")
    informe.verificar(
        "C6 Objetivos: selectores propios de Mes y Año (sin input type=month)",
        mes_select.count() == 1 and anio_select.count() == 1 and page.locator(".oc-period-bar input[type=month]").count() == 0,
        f"input month en la barra de período: {page.locator('.oc-period-bar input[type=month]').count()}",
    )
    if mes_select.count() == 1:
        opciones = [normalizar(t) for t in mes_select.locator("option").all_inner_texts()]
        informe.verificar(
            "C6 Objetivos: meses en español de enero a diciembre",
            opciones == MESES,
            opciones[:3],
        )
        mon.reiniciar()
        mes_select.select_option("04")
        esperar_pagina(page, 400)
        informe.verificar(
            "C6 Objetivos: elegir abril actualiza la URL y el período",
            "mes=2026-04" in page.url
            and page.evaluate("() => document.getElementById('periodoObjetivos')?.value") == "2026-04",
            page.url,
        )
    foto(page, carpeta, "objetivos-periodo")

    # C1: alta de una línea y de su duplicada exacta (mismo vendedor, mes, nivel y valor).
    ir(page, mon, f"/comercial/objetivos?mes={MES}")
    esperar_carga(page)
    primera = nueva_linea(page, DIEGO, "empresa", "LAC", EMPRESA, "150000")
    respuesta = enviar_linea(page, primera, "POST", "/api/objetivos-comerciales")
    informe.verificar("C1 Objetivos: la primera línea se guarda", respuesta.status == 201, respuesta.status)
    esperar_carga(page)
    page.wait_for_timeout(400)

    duplicada = nueva_linea(page, DIEGO, "empresa", "LAC", EMPRESA, "50000")
    respuesta = enviar_linea(page, duplicada, "POST", "/api/objetivos-comerciales")
    informe.verificar(
        "C1 Objetivos: la línea duplicada exacta se bloquea con 409",
        respuesta.status == 409,
        respuesta.status,
    )
    mensaje = normalizar(duplicada.locator("[data-line-error]").inner_text()) if duplicada.locator("[data-line-error]").count() else ""
    visible = duplicada.locator("[data-line-error]").is_visible() if duplicada.locator("[data-line-error]").count() else False
    informe.verificar(
        "C1 Objetivos: el mensaje en español se ve en la línea del formulario",
        visible and mensaje == MENSAJE_DUPLICADO,
        mensaje,
    )
    foto(page, carpeta, "objetivos-duplicada-mensaje")
    lineas = [l for l in lineas_api(ctx.request, MES, DIEGO) if l.get("dimension_valor") == EMPRESA]
    informe.verificar(
        "C1 Objetivos: la base queda con una sola línea de ese nivel y valor",
        len(lineas) == 1,
        f"líneas en base: {len(lineas)}",
    )
    informe.verificar(
        "Objetivos: sin errores de consola ni respuestas 4xx/5xx inesperadas",
        not mon.inesperados(ignorar=[(409, "/api/objetivos-comerciales")]),
        mon.inesperados(ignorar=[(409, "/api/objetivos-comerciales")])[:4],
    )
    ctx.close()


# ---------------------------------------------------------------------------
# Gastos: C2 (401/403 JSON y mensaje en español), C9 (sin categorías)
# ---------------------------------------------------------------------------
def caso_respuesta_gastos(ctx, informe, carpeta, nombre, respuesta_simulada, esperar_redireccion):
    page = ctx.new_page()
    mon = Monitor(page)
    page.route(
        "**/api/gastos/categorias*",
        lambda ruta: ruta.fulfill(**respuesta_simulada),
    )
    ir(page, mon, "/gastos", ms=800)
    mensaje = page.get_by_text(MENSAJE_SESION).count() > 0
    informe.verificar(f"C2 Gastos ({nombre}): muestra «{MENSAJE_SESION}»", mensaje)
    if esperar_redireccion:
        llego = esperar_js(page, "() => location.pathname === '/'", segundos=8) or any(
            ruta == "/" for ruta in mon.navegaciones
        )
        informe.verificar(f"C2 Gastos ({nombre}): redirige al login", llego, page.url)
    else:
        informe.verificar(
            f"C2 Gastos ({nombre}): no redirige, queda en Gastos",
            urlparse(page.url).path == "/gastos",
            page.url,
        )
    foto(page, carpeta, f"gastos-{nombre}")
    page.close()


def escenario_gastos(navegador, informe, carpeta):
    ctx = navegador.new_context(locale="es-AR", viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    mon = Monitor(page)
    informe.verificar("login admin para Gastos", login(page, ADMIN_USER, ADMIN_PASSWORD))
    page.close()

    # C9: sin categorías de egreso, el selector explica qué hacer y enlaza a Administración.
    page = ctx.new_page()
    mon = Monitor(page)
    page.route(
        "**/api/gastos/categorias*",
        lambda ruta: ruta.fulfill(status=200, content_type="application/json", body='{"categorias": []}'),
    )
    ir(page, mon, "/gastos")
    page.click('[data-bs-target="#modalNuevoGasto"]')
    expect(page.locator("#modalNuevoGasto")).to_be_visible(timeout=8000)
    texto_selector = normalizar(page.locator("#frmCategoria option").first.inner_text())
    informe.verificar(
        "C9 Gastos: sin categorías de egreso, el selector muestra el mensaje",
        texto_selector == "No hay categorías de egreso. Creá una en Administración",
        texto_selector,
    )
    enlace = page.locator("#modalNuevoGasto a", has_text="Administración")
    informe.verificar(
        "C9 Gastos: el mensaje tiene un enlace a Administración",
        enlace.count() > 0 and (enlace.first.get_attribute("href") or "").startswith("/admin"),
        enlace.first.get_attribute("href") if enlace.count() else "sin enlace",
    )
    foto(page, carpeta, "gastos-sin-categorias")
    page.close()

    # C2: respuestas no JSON o 401/403 muestran mensaje en español; 401 redirige al login.
    caso_respuesta_gastos(
        ctx, informe, carpeta, "401-json",
        {"status": 401, "content_type": "application/json", "body": '{"error": "Sesión requerida"}'},
        esperar_redireccion=True,
    )
    caso_respuesta_gastos(
        ctx, informe, carpeta, "403-json",
        {"status": 403, "content_type": "application/json", "body": '{"error": "Sin acceso al módulo"}'},
        esperar_redireccion=False,
    )
    caso_respuesta_gastos(
        ctx, informe, carpeta, "html-no-json",
        {"status": 200, "content_type": "text/html", "body": "<html><body>Inicie sesión</body></html>"},
        esperar_redireccion=False,
    )
    ctx.close()


def escenario_api_uniforme(navegador, informe):
    """C2 real, sin simulación: las rutas /api/* sin sesión o sin módulo responden JSON."""
    anonimo = navegador.new_context(locale="es-AR")
    casos = [
        ("/api/gastos/categorias", "sin sesión"),
        ("/api/comercial/salon", "sin sesión"),
        ("/api/tesoreria/movimientos", "sin sesión"),
        ("/api/objetivos-comerciales?mes=" + MES, "sin sesión"),
    ]
    for ruta, quien in casos:
        respuesta = anonimo.request.get(BASE_URL + ruta, max_redirects=0)
        tipo = respuesta.headers.get("content-type", "")
        informe.verificar(
            f"C2 API {ruta.split('?')[0]} ({quien}) responde 401 JSON",
            respuesta.status == 401 and "json" in tipo,
            f"{respuesta.status} {tipo}",
        )
    html = anonimo.request.get(BASE_URL + "/gastos", max_redirects=0)
    informe.verificar("C2 pantalla /gastos (sin sesión) sigue redirigiendo", html.status == 302, html.status)
    anonimo.close()

    ventas = navegador.new_context(locale="es-AR")
    page = ventas.new_page()
    informe.verificar("login ventas.demo para API", login(page, "ventas.demo", CLAVE_VENTAS))
    respuesta = ventas.request.get(BASE_URL + "/api/gastos/categorias", max_redirects=0)
    tipo = respuesta.headers.get("content-type", "")
    informe.verificar(
        "C2 API /api/gastos/categorias sin módulo responde 403 JSON",
        respuesta.status == 403 and "json" in tipo,
        f"{respuesta.status} {tipo}",
    )
    ventas.close()


# ---------------------------------------------------------------------------
# Ventas: C3 (clic en barra fija el filtro), C8 (selectores y cabeceras a 1280 px)
# ---------------------------------------------------------------------------
def clic_en_barra(page, canvas_id, indice):
    # Las coordenadas son del viewport: el canvas tiene que estar visible antes de medirlo.
    page.locator(f"#{canvas_id}").scroll_into_view_if_needed()
    time.sleep(0.2)
    return page.evaluate(
        """([id, i]) => {
            const c = Chart.getChart(document.getElementById(id));
            if (!c) return null;
            const r = c.canvas.getBoundingClientRect();
            const p = c.getDatasetMeta(0).data[i].getCenterPoint();
            return {x: r.left + p.x, y: r.top + p.y, labels: c.data.labels.map(String)};
        }""",
        [canvas_id, indice],
    )


def etiquetas_grafico(page, canvas_id):
    return page.evaluate(
        "(id) => { const c = Chart.getChart(document.getElementById(id)); return c ? c.data.labels.map(String) : null; }",
        canvas_id,
    )


def escenario_ventas(navegador, informe, carpeta):
    ctx = navegador.new_context(locale="es-AR", viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    mon = Monitor(page)
    informe.verificar("login admin para Ventas", login(page, ADMIN_USER, ADMIN_PASSWORD))
    ir(page, mon, "/dashboard-comercial", ms=800)
    listo = esperar_js(
        page,
        "() => { const c = Chart.getChart(document.getElementById('cantidad-ranking')); return !!c && c.data.labels.length > 1; }",
        segundos=30,
    )
    informe.verificar("Ventas: el ranking de cantidades se dibuja", listo)
    if not listo:
        return
    foto(page, carpeta, "ventas-antes-clic", completa=False)

    # C3: clic en una barra del ranking fija el filtro de producto de su sección.
    total_inicial = len(etiquetas_grafico(page, "cantidad-ranking") or [])
    punto = clic_en_barra(page, "cantidad-ranking", 0)
    nombre = punto["labels"][0]
    page.mouse.move(punto["x"], punto["y"])
    time.sleep(0.3)
    cursor = page.evaluate("() => document.getElementById('cantidad-ranking').style.cursor")
    informe.verificar("C3 Ventas: el cursor es pointer sobre la barra", cursor == "pointer", cursor)
    page.mouse.click(punto["x"], punto["y"])
    esperar_js(page, "() => document.querySelector('[data-com-filter-scope=analisis][data-com-filter-dimension=producto]')?.value !== ''", 8)
    esperar_pagina(page, 900)
    filtro = page.evaluate(
        "() => document.querySelector('[data-com-filter-scope=analisis][data-com-filter-dimension=producto]')?.value || ''"
    )
    informe.verificar(
        "C3 Ventas: el clic fija el filtro de producto de la sección",
        filtro == nombre and "analisis_producto=" in page.url,
        f"{filtro!r} / {page.url[-120:]}",
    )
    etiquetas = etiquetas_grafico(page, "cantidad-ranking") or []
    fijado = filtro == nombre and len(etiquetas) == 1
    informe.verificar(
        "C3 Ventas: el ranking se recarga con el filtro aplicado",
        len(etiquetas) == 1 and etiquetas[0] == nombre,
        f"barras: {len(etiquetas)} (antes {total_inicial})",
    )
    foto(page, carpeta, "ventas-clic-filtro-fijado", completa=False)

    punto = clic_en_barra(page, "cantidad-ranking", 0)
    page.mouse.click(punto["x"], punto["y"])
    esperar_pagina(page, 900)
    filtro = page.evaluate(
        "() => document.querySelector('[data-com-filter-scope=analisis][data-com-filter-dimension=producto]')?.value || ''"
    )
    etiquetas = etiquetas_grafico(page, "cantidad-ranking") or []
    informe.verificar(
        "C3 Ventas: un segundo clic en la misma barra limpia el filtro",
        fijado and filtro == "" and "analisis_producto" not in page.url and len(etiquetas) == total_inicial,
        f"filtro {filtro!r}, barras {len(etiquetas)}",
    )
    foto(page, carpeta, "ventas-clic-filtro-limpio", completa=False)

    # C3: teclado. La tabla de datos del ranking expone el mismo control con botones.
    tabla = page.locator("#cantidad-ranking-table")
    botones = tabla.locator("button")
    if tabla.locator("xpath=ancestor::details[1]").count():
        tabla.locator("xpath=ancestor::details[1]").first.locator("summary").first.click()
    informe.verificar("C3 Ventas: la tabla del ranking tiene controles de teclado", botones.count() > 0, botones.count())
    if botones.count():
        botones.first.focus()
        page.keyboard.press("Enter")
        esperar_pagina(page, 900)
        filtro_teclado = page.evaluate(
            "() => document.querySelector('[data-com-filter-scope=analisis][data-com-filter-dimension=producto]')?.value || ''"
        )
        informe.verificar(
            "C3 Ventas: Enter en la tabla fija el mismo filtro",
            filtro_teclado != "",
            filtro_teclado,
        )
        botones.first.focus()
        page.keyboard.press("Enter")
        esperar_pagina(page, 900)

    # C3: participación por producto (Mix).
    mon.reiniciar()
    page.locator("#mix-toggle").scroll_into_view_if_needed()
    esperar_js(page, "() => !!Chart.getChart(document.getElementById('mix-productos'))", 20)
    punto_mix = page.evaluate(
        """() => { const c = Chart.getChart(document.getElementById('mix-productos'));
            if (!c) return null; const r = c.canvas.getBoundingClientRect();
            const p = c.getDatasetMeta(0).data[0].getCenterPoint();
            return {x: r.left + p.x, y: r.top + p.y, label: String(c.data.labels[0])}; }"""
    )
    if punto_mix:
        punto_mix_label = punto_mix["label"]
        page.mouse.click(punto_mix["x"], punto_mix["y"])
        esperar_pagina(page, 900)
        filtro_mix = page.evaluate(
            "() => document.querySelector('[data-com-filter-scope=mix][data-com-filter-dimension=producto]')?.value || ''"
        )
        informe.verificar(
            "C3 Mix: el clic en Participación por producto fija el filtro de la sección",
            filtro_mix == punto_mix["label"] and "mix_producto=" in page.url,
            filtro_mix,
        )
        etiquetas_mix = etiquetas_grafico(page, "mix-productos") or []
        informe.verificar(
            "C3 Mix: la sección se recarga con el filtro",
            len(etiquetas_mix) == 1,
            f"segmentos: {len(etiquetas_mix)}",
        )
        punto_mix = page.evaluate(
            """() => { const c = Chart.getChart(document.getElementById('mix-productos'));
                const r = c.canvas.getBoundingClientRect();
                const p = c.getDatasetMeta(0).data[0].getCenterPoint();
                return {x: r.left + p.x, y: r.top + p.y}; }"""
        )
        page.mouse.click(punto_mix["x"], punto_mix["y"])
        esperar_pagina(page, 900)
        informe.verificar(
            "C3 Mix: un segundo clic limpia el filtro",
            filtro_mix == punto_mix_label and "mix_producto" not in page.url,
            page.url[-80:],
        )
    informe.verificar(
        "Ventas: sin errores de consola ni respuestas 4xx/5xx inesperadas",
        not mon.inesperados(),
        mon.inesperados()[:4],
    )

    # C8: a 1280 px, los selectores no cortan el texto y las cabeceras se ven completas.
    page.evaluate("() => window.scrollTo(0, 0)")
    recorte = page.evaluate(
        """() => {
            const items = [...document.querySelectorAll('.com-dimension-filters, .com-filter-dimension')]
                .flatMap(f => [...f.querySelectorAll('.ts-control .item, select')]);
            const resultado = [];
            for (const el of items) {
              const texto = (el.textContent || el.value || '').trim();
              if (!/Todos los (clientes|productos)/.test(texto)) continue;
              const visible = el.getBoundingClientRect().width > 0;
              const cortado = el.scrollWidth > el.clientWidth + 1;
              const puntos = getComputedStyle(el).textOverflow === 'ellipsis';
              resultado.push({texto, visible, cortado, puntos, title: el.title || ''});
            }
            return resultado;
        }"""
    )
    visibles = [r for r in recorte if r["visible"]]
    cortados = [r for r in visibles if r["cortado"] and not (r["puntos"] and r["title"])]
    informe.verificar(
        "C8 Ventas a 1280 px: «Todos los clientes/productos» no se corta",
        len(visibles) > 0 and not cortados,
        cortados or f"{len(visibles)} selectores revisados",
    )
    cabeceras = page.evaluate(
        """() => [...document.querySelectorAll('th, label, span, button, select, p, h2, h3')]
          .filter(el => el.offsetParent && /^\\s*(Medida|Importe|Cajas|Kilos)\\b/.test(el.textContent || ''))
          .filter(el => el.children.length === 0 || el.tagName === 'SELECT' || el.tagName === 'BUTTON')
          .map(el => ({texto: (el.textContent || el.value || '').trim().slice(0, 40), cortado: el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflow !== 'visible'}))"""
    )
    informe.verificar(
        "C8 Ventas a 1280 px: cabeceras Medida, Importe, Cajas y Kilos completas",
        not [c for c in cabeceras if c["cortado"]],
        [c["texto"] for c in cabeceras if c["cortado"]] or f"{len(cabeceras)} rótulos revisados",
    )
    foto(page, carpeta, "ventas-1280-selectores")
    ctx.close()


# ---------------------------------------------------------------------------
# RRHH: C4 (404 de liquidaciones como estado vacío, sin errores de consola)
# ---------------------------------------------------------------------------
def escenario_rrhh(navegador, informe, carpeta):
    ctx = navegador.new_context(locale="es-AR", viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    mon = Monitor(page)
    informe.verificar("login admin para RRHH", login(page, ADMIN_USER, ADMIN_PASSWORD))
    ir(page, mon, "/rrhh", ms=1000)
    informe.verificar(
        "RRHH: el panel carga sin errores de consola ni respuestas 4xx/5xx",
        not mon.inesperados(),
        mon.inesperados()[:4],
    )
    mon.reiniciar()
    page.fill("#periodoLiquidacion", "2099-01")
    page.dispatch_event("#periodoLiquidacion", "change")
    esperar_pagina(page, 900)
    texto = normalizar(page.locator("#tabla-liquidaciones").inner_text())
    esperado = "Todavía no hay liquidaciones para 2099-01"
    informe.verificar(
        "C4 RRHH: sin liquidaciones, el panel muestra el estado vacío en español",
        esperado in texto,
        texto[:120],
    )
    informe.verificar(
        "C4 RRHH: el período sin liquidaciones no deja errores de consola ni 404",
        not mon.inesperados(),
        mon.inesperados()[:4],
    )
    foto(page, carpeta, "rrhh-estado-vacio")
    ctx.close()


# ---------------------------------------------------------------------------
# Salón: C5 (Comprobante FAC visible y fechas en la URL)
# ---------------------------------------------------------------------------
def escenario_salon(navegador, informe, carpeta):
    ctx = navegador.new_context(locale="es-AR", viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    mon = Monitor(page)
    informe.verificar("login admin para Salón", login(page, ADMIN_USER, ADMIN_PASSWORD))
    ir(page, mon, "/comercial/salon", ms=800)
    informe.verificar(
        "C5 Salón: muestra el alcance «Comprobante: FAC»",
        page.get_by_text("Comprobante: FAC", exact=False).count() > 0,
    )
    desde = f"{MES}-01"
    hasta = f"{MES}-10"
    page.fill("#salon-filtros input[name=fecha_desde]", desde)
    page.fill("#salon-filtros input[name=fecha_hasta]", hasta)
    with page.expect_response(lambda r: "/api/comercial/salon" in r.url, timeout=15000):
        page.click("#salon-filtros button[type=submit]")
    esperar_pagina(page, 700)
    url = page.url
    informe.verificar(
        "C5 Salón: las fechas aplicadas quedan en la URL (?desde=&hasta=)",
        f"desde={desde}" in url and f"hasta={hasta}" in url,
        url[-80:],
    )
    total = normalizar(page.locator("#salon-tickets-total").inner_text())
    ir(page, mon, url.replace(BASE_URL, ""), ms=800)
    desde_cargado = page.input_value("#salon-filtros input[name=fecha_desde]")
    hasta_cargado = page.input_value("#salon-filtros input[name=fecha_hasta]")
    total_recargado = normalizar(page.locator("#salon-tickets-total").inner_text())
    informe.verificar(
        "C5 Salón: al abrir la URL carga las fechas y los mismos tickets",
        desde_cargado == desde and hasta_cargado == hasta and total_recargado == total,
        f"{desde_cargado}/{hasta_cargado} · {total_recargado}",
    )
    foto(page, carpeta, "salon-fac-fechas")
    ctx.close()


# ---------------------------------------------------------------------------
# Seguimiento: C8 (buscador con retardo de 300 ms)
# ---------------------------------------------------------------------------
def escenario_seguimiento(navegador, informe, carpeta):
    ctx = navegador.new_context(locale="es-AR", viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    mon = Monitor(page)
    informe.verificar("login admin para Seguimiento", login(page, ADMIN_USER, ADMIN_PASSWORD))
    ir(page, mon, "/comercial/seguimiento-clientes", ms=800)
    tiempos = []
    page.on(
        "request",
        lambda r: tiempos.append(time.time())
        if "/api/comercial/seguimiento-clientes" in r.url and "q=" in r.url
        else None,
    )
    campo = page.locator('input[name="q"]')
    campo.click()
    texto = "Cliente Demo 10"
    inicio = time.time()
    page.keyboard.type(texto, delay=40)
    fin_tecleo = time.time()
    page.wait_for_timeout(1400)
    peticiones = len(tiempos)
    primera = tiempos[0] if tiempos else None
    retardo = (primera - fin_tecleo) if primera else None
    informe.verificar(
        "C8 Seguimiento: el buscador filtra al escribir (sin Enter)",
        peticiones >= 1,
        f"peticiones con q: {peticiones}",
    )
    informe.verificar(
        "C8 Seguimiento: el filtro espera unos 300 ms tras la última tecla",
        peticiones == 1 and retardo is not None and 0.25 <= retardo <= 1.2,
        f"retardo {retardo:.2f} s" if retardo is not None else "sin petición",
    )
    cuenta = normalizar(page.locator("#com-list-count").inner_text())
    informe.verificar(
        "C8 Seguimiento: la lista muestra solo los clientes que coinciden",
        cuenta.startswith("1 cliente") or cuenta.startswith("0 cliente"),
        cuenta,
    )
    foto(page, carpeta, "seguimiento-busqueda")
    ctx.close()


# ---------------------------------------------------------------------------
# Admin y Friar: C9 (textos con tilde y sin prefijo técnico en arqueos)
# ---------------------------------------------------------------------------
def escenario_textos(navegador, informe, carpeta):
    ctx = navegador.new_context(locale="es-AR", viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    mon = Monitor(page)
    informe.verificar("login admin para textos", login(page, ADMIN_USER, ADMIN_PASSWORD))
    for ruta, esperado in (("/admin/tesoreria", "Administrar Tesorería"), ("/admin/rrhh", "Administrar RRHH")):
        ir(page, mon, ruta)
        titulo = normalizar(page.locator("h1").first.inner_text())
        informe.verificar(f"C9 Admin {ruta}: título «{esperado}»", titulo == esperado, titulo)

    ir(page, mon, "/tesoreria/cta-cte-friar")
    page.get_by_role("button", name="Liquidación").first.click()
    expect(page.locator("#modalNuevaLiquidacion")).to_be_visible(timeout=8000)
    titulo = normalizar(page.locator("#modalNuevaLiquidacionTitle").inner_text())
    informe.verificar(
        "C9 Cta Cte Friar: «Registrar liquidación Friar»",
        titulo == "Registrar liquidación Friar",
        titulo,
    )
    foto(page, carpeta, "friar-liquidacion-titulo")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # Arqueo duplicado: el servidor responde 400 con el mensaje; la pantalla no agrega «Error:».
    ir(page, mon, "/tesoreria/arqueos")
    mensajes = []
    page.on("dialog", lambda d: (mensajes.append(d.message), d.accept()))

    def rechazar_duplicado(ruta):
        if ruta.request.method == "POST":
            ruta.fulfill(
                status=400,
                content_type="application/json",
                body='{"error": "Ya existe arqueo para esa fecha y turno"}',
            )
        else:
            ruta.continue_()

    page.route("**/api/tesoreria/arqueos", rechazar_duplicado)
    page.click('[data-bs-target="#modalNuevoArqueo"]')
    expect(page.locator("#modalNuevoArqueo")).to_be_visible(timeout=8000)
    page.evaluate(
        """() => { const f = document.getElementById('formArqueo');
            for (const el of f.querySelectorAll('[required]')) {
              if (el.tagName === 'SELECT') { const o = [...el.options].find(o => o.value); if (o) el.value = o.value; }
              else if (el.type === 'date') el.value = new Date().toISOString().slice(0, 10);
              else if (!el.value) el.value = '1';
              el.dispatchEvent(new Event('change', {bubbles: true}));
            } }"""
    )
    page.click("#formArqueo button[type=submit]")
    esperar_pagina(page, 900)
    texto_pagina = normalizar(page.locator("body").inner_text())
    todos = [normalizar(m) for m in mensajes] + [texto_pagina]
    con_prefijo = any("Error: Ya existe arqueo" in t for t in todos)
    informe.verificar(
        "C9 Arqueos: el duplicado muestra el mensaje sin el prefijo «Error:»",
        any("Ya existe arqueo para esa fecha y turno" in t for t in todos) and not con_prefijo,
        " | ".join(m[:90] for m in mensajes) or "sin alerta",
    )
    foto(page, carpeta, "arqueos-duplicado")
    ctx.close()


# ---------------------------------------------------------------------------
# Accesibilidad: C7 (button-name y link-name en 390 px con axe-core)
# ---------------------------------------------------------------------------
def escenario_accesibilidad(navegador, informe, carpeta):
    if not os.path.exists(AXE_JS):
        informe.verificar("axe-core disponible", False, AXE_JS)
        return
    with open(AXE_JS, encoding="utf-8") as fh:
        axe_src = fh.read()
    ctx = navegador.new_context(locale="es-AR", viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    mon = Monitor(page)
    informe.verificar("login admin para accesibilidad", login(page, ADMIN_USER, ADMIN_PASSWORD))
    resumen = {}
    for nombre, ruta in RUTA_COBERTURA_ACCESIBILIDAD:
        ir(page, mon, ruta, ms=800)
        page.add_script_tag(content=axe_src)
        violaciones = page.evaluate(
            """async () => {
                const r = await axe.run(document, {resultTypes: ['violations']});
                return r.violations.map(v => ({id: v.id, impacto: v.impact,
                    nodos: v.nodes.map(n => ({target: n.target.join(' '), html: n.html.slice(0, 160)}))}));
            }"""
        )
        nombres = [v for v in violaciones if v["id"] in ("button-name", "link-name")]
        cantidad = sum(len(v["nodos"]) for v in nombres)
        resumen[nombre] = {
            "button_link_name": cantidad,
            "otras": sorted({v["id"] for v in violaciones if v["id"] not in ("button-name", "link-name")}),
            "nodos": [n for v in nombres for n in v["nodos"]][:40],
        }
        informe.verificar(
            f"C7 {nombre} a 390 px: 0 botones o enlaces sin nombre accesible",
            cantidad == 0,
            f"{cantidad} nodos",
        )
    carpeta_json = os.path.join(carpeta, "axe-390.json")
    os.makedirs(carpeta, exist_ok=True)
    with open(carpeta_json, "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, ensure_ascii=False, indent=2)
    ctx.close()


def resetear_datos():
    # -o: el daemon de la app no debe heredar el lock pesado.
    subprocess.run(["flock", "-o", LOCK, RUN_LOCAL, "reset"], check=True, capture_output=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--etiqueta", default="despues", help="antes o despues (carpeta de capturas)")
    parser.add_argument("--sin-reset", action="store_true", help="no reiniciar los datos sintéticos")
    parser.add_argument(
        "--solo",
        default="",
        help="lista separada por comas: objetivos,gastos,api,ventas,rrhh,salon,seguimiento,textos,a11y",
    )
    args = parser.parse_args()
    carpeta = os.path.join(CAPTURAS, args.etiqueta)
    os.makedirs(carpeta, exist_ok=True)
    if not args.sin_reset:
        print("== Reinicio de datos sintéticos", flush=True)
        resetear_datos()
    informe = Informe()
    escenarios = {
        "objetivos": escenario_objetivos,
        "gastos": escenario_gastos,
        "api": escenario_api_uniforme,
        "ventas": escenario_ventas,
        "rrhh": escenario_rrhh,
        "salon": escenario_salon,
        "seguimiento": escenario_seguimiento,
        "textos": escenario_textos,
        "a11y": escenario_accesibilidad,
    }
    elegidos = [s.strip() for s in args.solo.split(",") if s.strip()] or list(escenarios)
    with sync_playwright() as pw:
        chromium_args = ["--no-sandbox"]
        if urlparse(BASE_URL).port:
            chromium_args.append(f"--explicitly-allowed-ports={urlparse(BASE_URL).port}")
        navegador = pw.chromium.launch(executable_path=CHROMIUM, args=chromium_args)
        try:
            for nombre in elegidos:
                if nombre == "api":
                    ejecutar("C2 API uniforme", informe, escenario_api_uniforme, navegador, informe)
                elif nombre == "gastos":
                    ejecutar("C2/C9 Gastos", informe, escenario_gastos, navegador, informe, carpeta)
                elif nombre == "a11y":
                    ejecutar("C7 Accesibilidad", informe, escenarios[nombre], navegador, informe, carpeta)
                else:
                    ejecutar(nombre, informe, escenarios[nombre], navegador, informe, carpeta)
        finally:
            navegador.close()
    total, fallas = informe.guardar(os.path.join(carpeta, "informe.json"))
    print(f"\nTOTAL {total} · FALLAS {fallas} · capturas {carpeta}", flush=True)
    return 0 if fallas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
