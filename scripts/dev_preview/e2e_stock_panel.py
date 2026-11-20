"""Recorrido E2E del panel lateral de Stock (SIS-2B, corte 2), con Playwright en es-AR.

Qué verifica, con captura en cada pantalla tocada:
- Catálogos vacíos (sin productos ni ubicaciones): el panel muestra el aviso guiado con sus enlaces,
  «Guardar» y «Guardar y agregar otro» quedan deshabilitados, Escape cierra sin preguntar y el estado
  vacío de la lista abre el mismo panel.
- Con catálogo sintético: «Guardar» crea el registro, cierra el panel y la fila nueva aparece en la lista
  y en /api/stock. «Guardar y agregar otro» tres veces: el panel queda abierto, la ubicación se conserva,
  producto y cantidad se limpian, el aviso dice «Stock guardado: <producto> en <ubicación>», el foco vuelve
  al primer campo, y cada alta coincide en producto, ubicación y cantidad con la lista, la API y la base.
- Errores por campo: par repetido (422 con aviso en #stock-error-location_id y aria-invalid) y cantidad
  negativa (aviso en #stock-error-quantity).
- Escape con datos: pide confirmación (cancelar mantiene el panel; aceptar lo cierra y devuelve el foco).
  Escape sin datos cierra sin preguntar.
- Escapes: nombre con &, <b> y comillas se guarda y se muestra como texto (lista, panel y /stock/new).
- Pie visible a 1366×768 y los botones dentro de la ventana.
- /stock/new clásico: guarda con redirect a /stock y, con par repetido, avisa con su 409.
- Métricas: botones primarios con el panel cerrado y abierto, contraste del pie, errores de consola.

Datos sintéticos rotulados PROBE-STOCK-<sufijo>. Los productos y ubicaciones sintéticos se insertan en
la base E2E antes de la fase con catálogo; la fase de catálogos vacíos exige que la base no tenga ninguno.
Requisitos: la app en E2E_BASE_URL con la base E2E_DATABASE_URL recién creada; E2E_ADMIN_USER y
E2E_ADMIN_PASSWORD del admin de esa base. Capturas e informe JSON en E2E_CAPTURAS/<E2E_ETIQUETA>/.
Código de salida 0 solo si todas las verificaciones pasan.

Uso:
    E2E_BASE_URL=http://127.0.0.1:5094 E2E_DATABASE_URL=... E2E_ADMIN_PASSWORD=... \\
        /root/.cache/app360-e2e-venv/bin/python scripts/dev_preview/e2e_stock_panel.py --etiqueta despues
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime

import psycopg2
from playwright.sync_api import expect, sync_playwright

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5094").rstrip("/")
ADMIN_USER = os.environ.get("E2E_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("E2E_ADMIN_PASSWORD", "")
DB_URL = os.environ.get("E2E_DATABASE_URL", "").replace("postgresql+psycopg2://", "postgresql://")
CHROMIUM = os.environ.get("E2E_CHROMIUM", "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome")
CAPTURAS = os.environ.get("E2E_CAPTURAS", "/root/.hermes/cache/scratch/sis2b/capturas")
SUFIJO = datetime.now().strftime("%H%M%S")
PREFIJO = f"PROBE-STOCK-{SUFIJO}"

RESULTADOS = []
CONSOLA = []
ERRORES_PAGINA = []
INFORME = {"etiqueta": "", "base_url": BASE_URL, "verificaciones": RESULTADOS}
TOKEN_API = {}


def verificar(nombre, ok, detalle=""):
    RESULTADOS.append({"nombre": nombre, "ok": bool(ok), "detalle": str(detalle)})
    marca = "OK   " if ok else "FALLA"
    print(f"{marca} {nombre}" + (f" [{detalle}]" if detalle and not ok else ""))


def consulta(sql, params=()):
    with psycopg2.connect(DB_URL) as conexion, conexion.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def ejecutar(sql, params=()):
    with psycopg2.connect(DB_URL) as conexion, conexion.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()[0] if cursor.description else None


def captura(page, ventana, nombre):
    carpeta = os.path.join(CAPTURAS, INFORME["etiqueta"], ventana)
    os.makedirs(carpeta, exist_ok=True)
    page.screenshot(path=os.path.join(carpeta, f"{nombre}.png"))


def login(page):
    page.goto(BASE_URL + "/", wait_until="domcontentloaded")
    page.fill("#username", ADMIN_USER)
    page.fill("#password", ADMIN_PASSWORD)
    page.locator("form").filter(has=page.locator("#password")).locator("button[type=submit]").first.click()
    page.wait_for_load_state("load")


def cabeceras_api(origen):
    """JWT del admin para /api/stock. Se pide una vez: /api/login admite 5 intentos por minuto."""
    req = origen.request if hasattr(origen, "request") else origen
    if "token" not in TOKEN_API:
        respuesta = req.post(f"{BASE_URL}/api/login", data={"username": ADMIN_USER, "password": ADMIN_PASSWORD}, max_redirects=0)
        if respuesta.status != 200:
            return None
        TOKEN_API["token"] = respuesta.json()["access_token"]
    return {"Authorization": f"Bearer {TOKEN_API['token']}"}


def stock_api(origen):
    """Todas las filas de /api/stock (paginado, con JWT) como lista de dicts."""
    req = origen.request if hasattr(origen, "request") else origen
    cabeceras = cabeceras_api(origen)
    if cabeceras is None:
        return None
    filas = []
    numero = 1
    while True:
        respuesta = req.get(f"{BASE_URL}/api/stock?page={numero}&per_page=100", headers=cabeceras, max_redirects=0)
        if respuesta.status != 200:
            return None
        cuerpo = respuesta.json()
        filas.extend(cuerpo.get("items", []))
        if numero >= int(cuerpo.get("pages") or 1):
            return filas
        numero += 1


def luminancia(rgb):
    canales = []
    for valor in rgb[:3]:
        c = valor / 255
        canales.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * canales[0] + 0.7152 * canales[1] + 0.0722 * canales[2]


def contraste(texto, fondo):
    a, b = luminancia(texto), luminancia(fondo)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def rgb_de(texto):
    numeros = [float(n) for n in re.findall(r"[\d.]+", texto)]
    return numeros[:3] if len(numeros) >= 3 else (255, 255, 255)


def filas_stock(page):
    """Filas de la región de la lista: [id, producto, sku, ubicación, tipo, cantidad]."""
    filas = page.locator("[data-stock-region] tr[data-stock-id]")
    salida = []
    for i in range(filas.count()):
        celdas = [c.strip() for c in filas.nth(i).locator("td").all_inner_texts()]
        salida.append({"stock_id": filas.nth(i).get_attribute("data-stock-id"), "celdas": celdas})
    return salida


def fila_de(page, producto_nombre, ubicacion_nombre):
    coincidencias = [f for f in filas_stock(page) if f["celdas"][1] == producto_nombre and f["celdas"][3] == ubicacion_nombre]
    return coincidencias


def esperar_fila(page, producto_nombre, ubicacion_nombre, cantidad, segundos=10):
    """La lista se refresca de forma asíncrona tras guardar: se sondea hasta ver la fila nueva."""
    limite = time.time() + segundos
    while time.time() < limite:
        coincidencias = fila_de(page, producto_nombre, ubicacion_nombre)
        if len(coincidencias) == 1 and coincidencias[0]["celdas"][5] == str(cantidad):
            return coincidencias
        page.wait_for_timeout(200)
    return fila_de(page, producto_nombre, ubicacion_nombre)


def abrir_panel(page):
    page.locator('[data-drawer-open="stockPanel"]').first.click()
    expect(page.locator("#stockPanel")).to_be_visible()


def elegir(page, producto_id, ubicacion_id, cantidad):
    page.select_option("#product_id", str(producto_id))
    page.select_option("#location_id", str(ubicacion_id))
    page.fill("#stock-cantidad", str(cantidad))


def estado_panel(page):
    return page.locator("#stockPanel [data-drawer-status]").inner_text().strip()


def insertar_catalogo():
    productos = {}
    for clave, nombre in (
        ("p1", "PROBE-STOCK producto uno"),
        ("p2", "PROBE-STOCK producto dos"),
        ("p3", 'PROBE-STOCK Tom & <b>"Jerry"</b>'),
    ):
        productos[clave] = ejecutar(
            "INSERT INTO products (sku, name) VALUES (%s, %s) RETURNING id",
            (f"{PREFIJO}-{clave.upper()}", nombre),
        )
    ubicaciones = {}
    for clave, nombre, tipo in (
        ("l1", "PROBE-STOCK deposito norte", "nave"),
        ("l2", "PROBE-STOCK sucursal centro", "sucursal"),
        ("l3", "PROBE-STOCK deposito sur", "nave"),
    ):
        ubicaciones[clave] = ejecutar(
            "INSERT INTO locations (name, type, is_active) VALUES (%s, %s, true) RETURNING id",
            (nombre, tipo),
        )
    return productos, ubicaciones


NOMBRES = {
    "p1": "PROBE-STOCK producto uno",
    "p2": "PROBE-STOCK producto dos",
    "p3": 'PROBE-STOCK Tom & <b>"Jerry"</b>',
    "l1": "PROBE-STOCK deposito norte",
    "l2": "PROBE-STOCK sucursal centro",
    "l3": "PROBE-STOCK deposito sur",
}


def fase_catalogos_vacios(page):
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(BASE_URL + "/stock", wait_until="load")
    conteo = consulta("SELECT (SELECT count(*) FROM products), (SELECT count(*) FROM locations)")[0]
    verificar("catálogos vacíos: la base no tiene productos ni ubicaciones al empezar", conteo == (0, 0), conteo)
    if conteo != (0, 0):
        return False
    captura(page, "1440x900", "lista_vacia")
    verificar("lista vacía: estado vacío con su botón", page.locator("[data-stock-region] .empty-state").count() == 1)
    verificar(
        "lista vacía: un solo botón primario en la cabecera con el panel cerrado",
        page.locator(".panel-header .btn-primary:visible").count() == 1,
    )
    abrir_panel(page)
    captura(page, "1440x900", "panel_catalogo_vacio")
    verificar("catálogo vacío: aviso de productos con enlace", page.locator('#stockPanel a[href="/products/new"]').count() == 1)
    verificar("catálogo vacío: aviso de ubicaciones con enlace", page.locator('#stockPanel a[href="/locations/new"]').count() == 1)
    verificar(
        "catálogo vacío: «Guardar y agregar otro» deshabilitado",
        page.locator('#stockPanel [data-accion="agregar"]').is_disabled(),
    )
    verificar("catálogo vacío: «Guardar» deshabilitado", page.locator('#stockPanel [data-accion="guardar"]').is_disabled())
    page.keyboard.press("Escape")
    expect(page.locator("#stockPanel")).to_be_hidden(timeout=5000)
    verificar("catálogo vacío: Escape sin datos cierra sin confirmación", not page.locator("#app360ConfirmModal").is_visible())
    page.locator('[data-drawer-open="stockPanel"]', has_text="Cargar el primer stock").click()
    expect(page.locator("#stockPanel")).to_be_visible()
    verificar("catálogo vacío: el botón del estado vacío abre el mismo panel", page.locator("#stockPanel").is_visible())
    page.keyboard.press("Escape")
    expect(page.locator("#stockPanel")).to_be_hidden(timeout=5000)
    return True


def escenario_escritorio(page, productos, ubicaciones):
    p1, p2, p3 = productos["p1"], productos["p2"], productos["p3"]
    l1, l2 = ubicaciones["l1"], ubicaciones["l2"]
    page.goto(BASE_URL + "/stock", wait_until="load")
    verificar(
        "lista: un solo botón primario en la cabecera con el panel cerrado",
        page.locator(".panel-header .btn-primary:visible").count() == 1,
    )
    abrir_panel(page)
    verificar("panel: foco en el primer campo al abrir", page.evaluate("document.activeElement.id") == "product_id")
    captura(page, "1440x900", "panel_vacio")
    primarios = page.locator("#stockPanel .app-actions__primary:visible").count()
    verificar("panel: una sola acción primaria en el pie", primarios == 1, primarios)
    primario = page.evaluate(
        "(() => { const b = document.querySelector('#stockPanel .app-actions__primary');"
        " const s = getComputedStyle(b); return [s.color, s.backgroundColor]; })()"
    )
    ratio = contraste(rgb_de(primario[0]), rgb_de(primario[1]))
    verificar("pie: contraste del botón primario >= 4,5:1", ratio >= 4.5, round(ratio, 2))
    fondo = page.evaluate("getComputedStyle(document.querySelector('#stockPanel footer')).backgroundColor")
    color_sec = page.evaluate("getComputedStyle(document.querySelector('#stockPanel .app-actions__secondary')).color")
    ratio_sec = contraste(rgb_de(color_sec), rgb_de(fondo))
    verificar("pie: contraste del botón secundario >= 4,5:1", ratio_sec >= 4.5, round(ratio_sec, 2))

    # 1) Guardar: crea, cierra, resalta la fila y avisa
    elegir(page, p1, l1, 5)
    page.click('#stockPanel [data-accion="guardar"]')
    expect(page.locator("#stockPanel")).to_be_hidden(timeout=10000)
    expect(page.locator("[data-stock-region] tr[data-stock-id]").first).to_be_visible(timeout=10000)
    fila = esperar_fila(page, NOMBRES["p1"], NOMBRES["l1"], 5)
    verificar("guardar: la fila nueva aparece en la lista con producto, ubicación y cantidad", len(fila) == 1 and fila[0]["celdas"][5] == "5", fila)
    verificar("guardar: el foco vuelve al botón de la cabecera", page.evaluate("document.activeElement.dataset.drawerOpen") == "stockPanel")
    verificar("guardar: aviso «Stock guardado: producto uno en deposito norte»", page.get_by_text(f"Stock guardado: {NOMBRES['p1']} en {NOMBRES['l1']}").first.is_visible())
    api = stock_api(page) or []
    verificar("guardar: el registro está en /api/stock", any(i["product_id"] == p1 and i["location_id"] == l1 and i["quantity"] == 5 for i in api))
    verificar("guardar: persistido en la base", consulta("SELECT quantity FROM stock_levels WHERE product_id=%s AND location_id=%s", (p1, l1)) == [(5,)])
    captura(page, "1440x900", "tras_guardar")

    # 2) Guardar y agregar otro, tres veces: la ubicación se conserva
    altas = [(p2, l1, 3, NOMBRES["p2"], NOMBRES["l1"]), (p1, l2, 4, NOMBRES["p1"], NOMBRES["l2"]), (p2, l2, 2, NOMBRES["p2"], NOMBRES["l2"])]
    abrir_panel(page)
    for indice, (producto_id, ubicacion_id, cantidad, nombre_p, nombre_l) in enumerate(altas, start=1):
        elegir(page, producto_id, ubicacion_id, cantidad)
        page.click('#stockPanel [data-accion="agregar"]')
        expect(page.locator("#stockPanel [data-drawer-status]")).to_have_text(f"Stock guardado: {nombre_p} en {nombre_l}", timeout=10000)
        verificar(f"agregar otro {indice}: panel abierto tras guardar", page.locator("#stockPanel").is_visible())
        verificar(
            f"agregar otro {indice}: la ubicación se conserva ({nombre_l})",
            page.input_value("#location_id") == str(ubicacion_id),
        )
        verificar(f"agregar otro {indice}: la cantidad vuelve a 0", page.input_value("#stock-cantidad") == "0")
        verificar(f"agregar otro {indice}: foco en el primer campo", page.evaluate("document.activeElement.id") == "product_id")
        expect(page.locator("[data-stock-region] tr[data-stock-id]").first).to_be_visible(timeout=10000)
        fila = esperar_fila(page, nombre_p, nombre_l, cantidad)
        verificar(f"agregar otro {indice}: la lista muestra {nombre_p} en {nombre_l} con {cantidad}", len(fila) == 1 and fila[0]["celdas"][5] == str(cantidad), fila)
        api = stock_api(page) or []
        verificar(
            f"agregar otro {indice}: /api/stock coincide con la pantalla",
            any(i["product_id"] == producto_id and i["location_id"] == ubicacion_id and i["quantity"] == cantidad for i in api),
        )
        verificar(
            f"agregar otro {indice}: la base coincide",
            consulta("SELECT quantity FROM stock_levels WHERE product_id=%s AND location_id=%s", (producto_id, ubicacion_id)) == [(cantidad,)],
        )
        if indice == 1:
            captura(page, "1440x900", "tras_agregar_otro")
    verificar("agregar otro: la lista tiene los 4 registros de este recorrido", len([f for f in filas_stock(page) if f["celdas"][1].startswith("PROBE-STOCK")]) == 4)

    # 3) Errores por campo
    elegir(page, p2, l1, 1)  # par ya cargado en el paso 2 (P2 en L1 = 3)
    page.click('#stockPanel [data-accion="agregar"]')
    expect(page.locator("#stock-error-location_id")).to_be_visible(timeout=10000)
    verificar("error par repetido: aviso junto a la ubicación", "Ya hay stock de este producto en esa ubicación (3)" in page.inner_text("#stock-error-location_id"))
    verificar("error par repetido: aria-invalid en la ubicación", page.get_attribute("#location_id", "aria-invalid") == "true")
    verificar("error par repetido: el foco va a la ubicación", page.evaluate("document.activeElement.id") == "location_id")
    verificar("error par repetido: no pisa el registro", consulta("SELECT quantity FROM stock_levels WHERE product_id=%s AND location_id=%s", (p2, l1)) == [(3,)])
    captura(page, "1440x900", "panel_error")
    elegir(page, p1, l1, "-1")
    page.click('#stockPanel [data-accion="guardar"]')
    expect(page.locator("#stock-error-quantity")).to_be_visible(timeout=10000)
    verificar("error cantidad: aviso «no puede ser negativa»", "no puede ser negativa" in page.inner_text("#stock-error-quantity"))
    verificar("error cantidad: aria-invalid en la cantidad", page.get_attribute("#stock-cantidad", "aria-invalid") == "true")

    # 4) Escape con datos: confirmación; cancelar mantiene el panel
    page.fill("#stock-cantidad", "9")
    page.keyboard.press("Escape")
    expect(page.locator("#app360ConfirmModal")).to_be_visible(timeout=5000)
    page.wait_for_timeout(600)  # termina la transición de apertura del modal
    verificar("escape con datos: pide confirmación", True)
    page.click("#app360ConfirmCancel")
    expect(page.locator("#app360ConfirmModal")).to_be_hidden(timeout=5000)
    page.wait_for_timeout(600)
    verificar("escape con datos: cancelar mantiene el panel abierto", page.locator("#stockPanel").is_visible())
    page.keyboard.press("Escape")
    expect(page.locator("#app360ConfirmModal")).to_be_visible(timeout=5000)
    page.wait_for_timeout(600)
    page.click("#app360ConfirmAccept")
    expect(page.locator("#stockPanel")).to_be_hidden(timeout=5000)
    verificar("escape con datos: confirmar cierra y devuelve el foco al botón", page.evaluate("document.activeElement.dataset.drawerOpen") == "stockPanel")
    verificar("escape con datos: no guardó el borrador", consulta("SELECT count(*) FROM stock_levels WHERE quantity=9")[0][0] == 0)

    # 5) Escape sin datos: cierra sin preguntar
    abrir_panel(page)
    page.keyboard.press("Escape")
    expect(page.locator("#stockPanel")).to_be_hidden(timeout=5000)
    verificar("escape sin datos: cierra sin confirmación", not page.locator("#app360ConfirmModal").is_visible())

    # 6) Escapes: nombre con &, <b> y comillas se muestra como texto
    abrir_panel(page)
    elegir(page, p3, l1, 1)
    page.click('#stockPanel [data-accion="guardar"]')
    expect(page.locator("#stockPanel")).to_be_hidden(timeout=10000)
    expect(page.locator("[data-stock-region] tr[data-stock-id]").first).to_be_visible(timeout=10000)
    nombre_raro = NOMBRES["p3"]
    fila = esperar_fila(page, nombre_raro, NOMBRES["l1"], 1)
    verificar("escapes: el nombre se muestra como texto literal en la lista", len(fila) == 1, [f["celdas"][:2] for f in filas_stock(page)][:3])
    verificar("escapes: no aparece marcado <b> en la lista", page.locator("[data-stock-region] b").count() == 0)
    opciones = page.locator("#stockPanel #product_id option").all_inner_texts()
    verificar("escapes: el panel muestra el nombre como texto", any("<b>" in o and "Tom & " in o for o in opciones))
    verificar(
        "escapes: la API devuelve el registro del producto con marcado",
        any(i["product_id"] == p3 and i["location_id"] == l1 for i in (stock_api(page) or [])),
    )

    # 7) /stock/new clásico: guarda con redirect a la lista; par repetido avisa con 409
    page.goto(BASE_URL + "/stock/new", wait_until="load")
    page.select_option("#product_id", str(p3))
    page.select_option("#location_id", str(l2))
    page.fill("#stock-cantidad", "6")
    page.click("form:has(#stock-cantidad) button[type=submit]")
    page.wait_for_url(re.compile(r".*/stock/?$"), timeout=10000)
    verificar("formulario clásico: redirige a la lista tras guardar", page.url.rstrip("/").endswith("/stock"))
    verificar("formulario clásico: persistido", consulta("SELECT quantity FROM stock_levels WHERE product_id=%s AND location_id=%s", (p3, l2)) == [(6,)])
    page.goto(BASE_URL + "/stock/new", wait_until="load")
    page.select_option("#product_id", str(p3))
    page.select_option("#location_id", str(l2))
    page.fill("#stock-cantidad", "1")
    page.click("form:has(#stock-cantidad) button[type=submit]")
    expect(page.get_by_text("Ya hay stock de este producto en esa ubicación (6)").first).to_be_visible(timeout=10000)
    verificar("formulario clásico: par repetido avisa y no pisa", consulta("SELECT quantity FROM stock_levels WHERE product_id=%s AND location_id=%s", (p3, l2)) == [(6,)])
    captura(page, "1440x900", "clasico_repetido")


def escenario_1366(page, productos, ubicaciones):
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(BASE_URL + "/stock", wait_until="load")
    captura(page, "1366x768", "lista")
    abrir_panel(page)
    captura(page, "1366x768", "panel_vacio")
    pie = page.evaluate(
        "(() => { const f = document.querySelector('#stockPanel footer').getBoundingClientRect();"
        " const botones = [...document.querySelectorAll('#stockPanel [data-drawer-pie] button')]"
        ".map(b => b.getBoundingClientRect()); return {bottom: f.bottom, botones: botones.map(r => [r.top, r.bottom])}; })()"
    )
    dentro = pie["bottom"] <= 768 and all(0 <= r[0] and r[1] <= 768 for r in pie["botones"])
    verificar("1366x768: pie y botones dentro de la ventana", dentro, pie)
    # Par nuevo (producto dos en depósito sur): los seis pares de los pasos de escritorio ya existen.
    elegir(page, productos["p2"], ubicaciones["l3"], 2)
    page.click('#stockPanel [data-accion="agregar"]')
    expect(page.locator("#stockPanel [data-drawer-status]")).to_have_text(
        f"Stock guardado: {NOMBRES['p2']} en {NOMBRES['l3']}", timeout=10000
    )
    captura(page, "1366x768", "tras_agregar_otro")
    elegir(page, productos["p2"], ubicaciones["l3"], 1)
    page.click('#stockPanel [data-accion="agregar"]')
    expect(page.locator("#stock-error-location_id")).to_be_visible(timeout=10000)
    captura(page, "1366x768", "panel_error")
    page.keyboard.press("Escape")
    expect(page.locator("#app360ConfirmModal")).to_be_visible(timeout=5000)
    page.wait_for_timeout(600)
    page.click("#app360ConfirmAccept")
    expect(page.locator("#stockPanel")).to_be_hidden(timeout=5000)
    verificar("1366x768: Escape con datos y confirmación cierra el panel", True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--etiqueta", default=os.environ.get("E2E_ETIQUETA", "despues"))
    args = parser.parse_args()
    INFORME["etiqueta"] = args.etiqueta
    if not DB_URL or not ADMIN_PASSWORD:
        print("Faltan E2E_DATABASE_URL o E2E_ADMIN_PASSWORD.")
        return 2

    with sync_playwright() as p:
        navegador = p.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        contexto = navegador.new_context(viewport={"width": 1440, "height": 900}, locale="es-AR")
        page = contexto.new_page()
        page.on("console", lambda m: CONSOLA.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: ERRORES_PAGINA.append(str(e)))
        login(page)
        verificar("login del admin", "/login" not in page.url and page.locator("#password").count() == 0)
        vacio = fase_catalogos_vacios(page)
        productos, ubicaciones = insertar_catalogo()
        INFORME["catalogo_sintetico"] = {"productos": productos, "ubicaciones": ubicaciones}
        page.goto(BASE_URL + "/stock", wait_until="load")
        escenario_escritorio(page, productos, ubicaciones)
        escenario_1366(page, productos, ubicaciones)
        navegador.close()

    recursos = [m for m in CONSOLA if m.startswith("Failed to load resource")]
    validacion = [m for m in recursos if "status of 422" in m or "status of 409" in m]
    favicon = [m for m in recursos if "status of 404" in m]
    inesperados = [m for m in CONSOLA if m not in validacion and m not in favicon]
    verificar("consola: sin errores de JavaScript ni recursos inesperados", not inesperados and not ERRORES_PAGINA, inesperados or ERRORES_PAGINA)
    INFORME["consola_recursos_esperados"] = {"422_409_validacion": len(validacion), "404_favicon": len(favicon)}
    INFORME["catalogo_vacio_probado"] = vacio
    fallas = [r for r in RESULTADOS if not r["ok"]]
    INFORME["resumen"] = {"total": len(RESULTADOS), "ok": len(RESULTADOS) - len(fallas), "fallas": len(fallas)}
    os.makedirs(os.path.join(CAPTURAS, args.etiqueta), exist_ok=True)
    with open(os.path.join(CAPTURAS, args.etiqueta, "informe.json"), "w", encoding="utf-8") as archivo:
        json.dump(INFORME, archivo, ensure_ascii=False, indent=2)
    print(f"RESUMEN {INFORME['resumen']}")
    return 0 if not fallas else 1


if __name__ == "__main__":
    sys.exit(main())
