"""Recorrido E2E del panel lateral de altas de Productos (SIS-2B, corte 1), con Playwright en es-AR.

Qué verifica, con captura en cada pantalla tocada:
- Panel desde la lista: abre, foco al primer campo y vuelve al botón al cerrar.
- «Guardar»: crea el producto, cierra el panel, lo muestra en la tabla resaltado y en /api/products.
- «Guardar y agregar otro» tres veces seguidas: el panel queda abierto, los campos se limpian (SKU y
  nombre), se conservan unidad de negocio y categoría, y cada producto aparece en la tabla y en la API.
- Error por campo: SKU repetido (422 con aviso en #producto-error-sku y aria-invalid) y nombre vacío.
- Escape: con datos sin guardar pide confirmación (cancelar la mantiene abierta; aceptar la cierra);
  sin datos cierra sin preguntar. El foco vuelve al botón que abrió el panel.
- Pie visible a 1366×768 y los botones dentro de la ventana.
- Escapes: nombre con «&», «<b>» y comillas se guarda y se muestra como texto.
- /products/new clásico: sigue guardando y redirige a la lista.
- Métricas: botones primarios de la cabecera y del panel, contraste del pie, errores de consola.

Datos sintéticos rotulados PROBE-PANEL-<sufijo>; la unidad de negocio PROBE-E2E se crea si no existe.
Requisitos: la app en E2E_BASE_URL con la base E2E_DATABASE_URL reiniciada; E2E_ADMIN_USER y
E2E_ADMIN_PASSWORD del admin de esa base. Capturas e informe JSON en E2E_CAPTURAS/<E2E_ETIQUETA>/.
Código de salida 0 solo si todas las verificaciones pasan.

Uso:
    E2E_BASE_URL=http://127.0.0.1:5094 E2E_DATABASE_URL=... E2E_ADMIN_PASSWORD=... \
        /root/.cache/app360-e2e-venv/bin/python scripts/dev_preview/e2e_altas_panel.py --etiqueta despues
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

import psycopg2
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from e2e_objetivos_helpers import entero  # noqa: E402  (reutilizado: redondeo de cifras de la pantalla)

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5094").rstrip("/")
ADMIN_USER = os.environ.get("E2E_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("E2E_ADMIN_PASSWORD", "")
DB_URL = os.environ.get("E2E_DATABASE_URL", "").replace("postgresql+psycopg2://", "postgresql://")
CHROMIUM = os.environ.get("E2E_CHROMIUM", "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome")
CAPTURAS = os.environ.get("E2E_CAPTURAS", "/root/.hermes/cache/scratch/e2e-altas-panel/capturas")
SUFIJO = datetime.now().strftime("%H%M%S")
PREFIJO_SKU = f"PROBE-PANEL-{SUFIJO}"
NOMBRE_UNIDAD = "PROBE-E2E Unidad panel"
CATEGORIA = "PROBE-panel"
VENTANAS = {"1440x900": (1440, 900), "1366x768": (1366, 768)}

RESULTADOS = []
CONSOLA = []
ERRORES_PAGINA = []
INFORME = {"etiqueta": "", "base_url": BASE_URL, "verificaciones": RESULTADOS}


def verificar(nombre, ok, detalle=""):
    RESULTADOS.append({"nombre": nombre, "ok": bool(ok), "detalle": str(detalle)})
    marca = "OK  " if ok else "FALLA"
    print(f"{marca} {nombre}" + (f" [{detalle}]" if detalle and not ok else ""))


def consulta(sql, params=()):
    with psycopg2.connect(DB_URL) as conexion, conexion.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def unidad_id():
    filas = consulta("SELECT id FROM business_units WHERE name=%s ORDER BY id LIMIT 1", (NOMBRE_UNIDAD,))
    if filas:
        return filas[0][0]
    with psycopg2.connect(DB_URL) as conexion, conexion.cursor() as cursor:
        cursor.execute("INSERT INTO business_units (name) VALUES (%s) RETURNING id", (NOMBRE_UNIDAD,))
        return cursor.fetchone()[0]


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


TOKEN_API = {}


def cabeceras_api(origen):
    """JWT del admin para /api/products. Se pide una vez: /api/login admite 5 intentos por minuto."""
    req = origen.request if hasattr(origen, "request") else origen
    if "token" not in TOKEN_API:
        respuesta = req.post(f"{BASE_URL}/api/login", data={"username": ADMIN_USER, "password": ADMIN_PASSWORD}, max_redirects=0)
        if respuesta.status != 200:
            return None
        TOKEN_API["token"] = respuesta.json()["access_token"]
    return {"Authorization": f"Bearer {TOKEN_API['token']}"}


def productos_api(origen):
    """Todos los productos de /api/products (paginado, con JWT), indexados por SKU."""
    req = origen.request if hasattr(origen, "request") else origen
    cabeceras = cabeceras_api(origen)
    if cabeceras is None:
        return None
    por_sku = {}
    numero = 1
    while True:
        respuesta = req.get(f"{BASE_URL}/api/products?page={numero}&per_page=100", headers=cabeceras, max_redirects=0)
        if respuesta.status != 200:
            return None
        cuerpo = respuesta.json()
        for item in cuerpo.get("items", []):
            por_sku[item.get("sku")] = item
        if numero >= int(cuerpo.get("pages") or 1):
            return por_sku
        numero += 1


def abrir_panel(page):
    page.locator('[data-drawer-open="productoPanel"]').first.click()
    expect(page.locator("#productoPanel")).to_be_visible()


def campos(page, sku, nombre, categoria=CATEGORIA, unidad=None):
    page.fill("#producto-sku", sku)
    page.fill("#producto-nombre", nombre)
    page.select_option("#business_unit_id", str(unidad))
    page.fill("#producto-categoria", categoria)


def estado_panel(page):
    return page.locator("#productoPanel [data-drawer-status]").inner_text().strip()


def fila_de(page, sku):
    return page.locator(f'[data-products-region] tr[data-product-id]:has(td:text-is("{sku}"))')


def esperar_en_lista(page, sku, nombre_mostrado=None):
    expect(fila_de(page, sku)).to_have_count(1, timeout=10000)
    return fila_de(page, sku)


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


def escenario_escritorio(page, unidad, skus):
    s1, s2, s3, s4 = (f"{PREFIJO_SKU}-{n}" for n in (1, 2, 3, 4))
    page.goto(BASE_URL + "/products", wait_until="load")
    captura(page, "1440x900", "lista")
    verificar(
        "lista: un solo botón primario en la cabecera con el panel cerrado",
        page.locator(".panel-header .btn-primary:visible").count() == 1,
    )

    abrir_panel(page)
    verificar("panel: foco en el primer campo al abrir", page.evaluate("document.activeElement.id") == "producto-sku")
    captura(page, "1440x900", "panel_vacio")
    primarios = page.locator("#productoPanel .app-actions__primary:visible").count()
    verificar("panel: una sola acción primaria en el pie", primarios == 1, primarios)
    primario_color = page.evaluate(
        "(() => { const b = document.querySelector('#productoPanel .app-actions__primary');"
        " const s = getComputedStyle(b); return [s.color, s.backgroundColor]; })()"
    )
    ratio = contraste(rgb_de(primario_color[0]), rgb_de(primario_color[1]))
    verificar("pie: contraste del botón primario >= 4,5:1", ratio >= 4.5, round(ratio, 2))
    secundario_fondo = page.evaluate(
        "getComputedStyle(document.querySelector('#productoPanel footer')).backgroundColor"
    )
    secundario_color = page.evaluate(
        "getComputedStyle(document.querySelector('#productoPanel .app-actions__secondary')).color"
    )
    ratio_sec = contraste(rgb_de(secundario_color), rgb_de(secundario_fondo))
    verificar("pie: contraste del botón secundario >= 4,5:1", ratio_sec >= 4.5, round(ratio_sec, 2))

    # 1) Guardar
    campos(page, s1, "PROBE panel uno", unidad=unidad)
    page.click('#productoPanel [data-accion="guardar"]')
    expect(page.locator("#productoPanel")).to_be_hidden(timeout=10000)
    fila = esperar_en_lista(page, s1)
    verificar("guardar: el producto aparece en la tabla", fila.count() == 1)
    verificar(
        "guardar: el foco vuelve al botón «Nuevo Producto»",
        page.evaluate("document.activeElement.dataset.drawerOpen") == "productoPanel",
    )
    verificar("guardar: aviso de confirmación", page.get_by_text("Producto «PROBE panel uno» guardado").first.is_visible())
    api = productos_api(page) or {}
    verificar("guardar: el producto está en /api/products", s1 in api and api[s1]["name"] == "PROBE panel uno")
    verificar("guardar: persistido en la base", consulta("SELECT count(*) FROM products WHERE sku=%s", (s1,))[0][0] == 1)
    captura(page, "1440x900", "tras_guardar")
    skus.append(s1)

    # 2) Guardar y agregar otro, tres veces seguidas
    abrir_panel(page)
    for sku, nombre in ((s2, "PROBE panel dos"), (s3, "PROBE panel tres"), (s4, "PROBE panel cuatro")):
        campos(page, sku, nombre, unidad=unidad)
        page.click('#productoPanel [data-accion="agregar"]')
        expect(page.locator("#productoPanel [data-drawer-status]")).to_have_text(f"Producto «{nombre}» guardado", timeout=10000)
        verificar(f"agregar otro: panel abierto tras «{nombre}»", page.locator("#productoPanel").is_visible())
        verificar(
            f"agregar otro: campos limpios tras «{nombre}» (SKU y nombre)",
            page.input_value("#producto-sku") == "" and page.input_value("#producto-nombre") == "",
        )
        verificar(
            f"agregar otro: conserva unidad y categoría tras «{nombre}»",
            page.input_value("#business_unit_id") == str(unidad) and page.input_value("#producto-categoria") == CATEGORIA,
        )
        verificar(
            f"agregar otro: foco en el SKU tras «{nombre}»",
            page.evaluate("document.activeElement.id") == "producto-sku",
        )
        esperar_en_lista(page, sku)
        api = productos_api(page) or {}
        verificar(f"agregar otro: «{nombre}» aparece en /api/products", sku in api and api[sku]["name"] == nombre)
        skus.append(sku)
        if sku == s2:
            captura(page, "1440x900", "tras_agregar_otro")
    verificar(
        "agregar otro: la tabla de fondo suma los productos (total de la fila de pie)",
        entero(page.locator("tfoot [data-format-number]").inner_text().replace(".", "")) >= 4,
    )

    # 3) Error de SKU repetido: aviso por campo
    campos(page, s1, "PROBE repetido", unidad=unidad)
    page.click('#productoPanel [data-accion="agregar"]')
    expect(page.locator("#producto-error-sku")).to_be_visible(timeout=10000)
    verificar("error SKU: aviso junto al campo", page.inner_text("#producto-error-sku") == "El SKU ya existe.")
    verificar("error SKU: aria-invalid en el campo", page.get_attribute("#producto-sku", "aria-invalid") == "true")
    verificar("error SKU: el foco va al campo con error", page.evaluate("document.activeElement.id") == "producto-sku")
    verificar("error SKU: no crea un segundo producto", consulta("SELECT count(*) FROM products WHERE sku=%s", (s1,))[0][0] == 1)
    captura(page, "1440x900", "panel_error")

    # 4) Error de nombre vacío
    page.fill("#producto-sku", f"{PREFIJO_SKU}-VACIO")
    page.fill("#producto-nombre", "")
    page.click('#productoPanel [data-accion="guardar"]')
    expect(page.locator("#producto-error-name")).to_be_visible(timeout=10000)
    verificar("error nombre: aviso «Ingresá el nombre del producto.»", page.inner_text("#producto-error-name") == "Ingresá el nombre del producto.")

    # 5) Escape con datos: confirmación, cancelar mantiene el panel
    page.fill("#producto-nombre", "PROBE sin guardar")
    page.keyboard.press("Escape")
    expect(page.locator("#app360ConfirmModal")).to_be_visible(timeout=5000)
    # Bootstrap ignora hide() durante la transición de apertura: se espera a que termine.
    page.wait_for_timeout(600)
    verificar("escape con datos: pide confirmación", True)
    page.click("#app360ConfirmCancel")
    expect(page.locator("#app360ConfirmModal")).to_be_hidden(timeout=5000)
    page.wait_for_timeout(600)  # termina la transición de cierre del modal antes del siguiente Escape
    verificar("escape con datos: cancelar mantiene el panel abierto", page.locator("#productoPanel").is_visible())

    # 6) Escape con datos y confirmación: cierra y devuelve el foco
    page.keyboard.press("Escape")
    expect(page.locator("#app360ConfirmModal")).to_be_visible(timeout=5000)
    # Bootstrap ignora hide() durante la transición de apertura: se espera a que termine.
    page.wait_for_timeout(600)
    page.click("#app360ConfirmAccept")
    expect(page.locator("#app360ConfirmModal")).to_be_hidden(timeout=5000)
    expect(page.locator("#productoPanel")).to_be_hidden(timeout=5000)
    verificar(
        "escape con datos: confirmar cierra y devuelve el foco al botón",
        page.evaluate("document.activeElement.dataset.drawerOpen") == "productoPanel",
    )
    verificar("escape con datos: no guardó el borrador", consulta("SELECT count(*) FROM products WHERE name=%s", ("PROBE sin guardar",))[0][0] == 0)

    # 7) Escape sin datos: cierra sin preguntar
    abrir_panel(page)
    page.keyboard.press("Escape")
    expect(page.locator("#productoPanel")).to_be_hidden(timeout=5000)
    verificar("escape sin datos: cierra sin confirmación", not page.locator("#app360ConfirmModal").is_visible())

    # 8) Nombre con &, <b> y comillas: texto literal
    nombre_raro = 'PROBE Tom & <b>"Jerry"</b>'
    sku_raro = f"{PREFIJO_SKU}-ESC"
    abrir_panel(page)
    campos(page, sku_raro, nombre_raro, unidad=unidad)
    page.click('#productoPanel [data-accion="guardar"]')
    expect(page.locator("#productoPanel")).to_be_hidden(timeout=10000)
    fila = esperar_en_lista(page, sku_raro)
    verificar("escapes: el nombre se muestra como texto literal", nombre_raro in fila.inner_text())
    verificar("escapes: no aparece marcado <b> en la tabla", page.locator('[data-products-region] b').count() == 0)
    api = productos_api(page) or {}
    verificar("escapes: la API devuelve el nombre exacto", api.get(sku_raro, {}).get("name") == nombre_raro)
    skus.append(sku_raro)

    # 9) /products/new clásico sigue guardando con redirect
    sku_clasico = f"{PREFIJO_SKU}-CLASICO"
    page.goto(BASE_URL + "/products/new", wait_until="load")
    page.fill("input[name=sku]", sku_clasico)
    page.fill("input[name=name]", "PROBE clasico")
    page.select_option("select[name=business_unit_id]", str(unidad))
    page.click("form:has(input[name=sku]) button[type=submit]")
    page.wait_for_url(re.compile(r".*/products/?$"), timeout=10000)
    verificar("formulario clásico: redirige a la lista tras guardar", page.url.rstrip("/").endswith("/products"))
    verificar("formulario clásico: persistido", consulta("SELECT count(*) FROM products WHERE sku=%s", (sku_clasico,))[0][0] == 1)
    skus.append(sku_clasico)


def escenario_1366(page, unidad, skus):
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(BASE_URL + "/products", wait_until="load")
    captura(page, "1366x768", "lista")
    abrir_panel(page)
    captura(page, "1366x768", "panel_vacio")
    alto = 768
    pie = page.evaluate(
        "(() => { const f = document.querySelector('#productoPanel footer').getBoundingClientRect();"
        " const botones = [...document.querySelectorAll('#productoPanel [data-drawer-pie] button')]"
        ".map(b => b.getBoundingClientRect()); return {bottom: f.bottom, botones: botones.map(r => [r.top, r.bottom])}; })()"
    )
    dentro = pie["bottom"] <= alto and all(0 <= r[0] and r[1] <= alto for r in pie["botones"])
    verificar("1366x768: pie y botones dentro de la ventana", dentro, pie)
    sku = f"{PREFIJO_SKU}-768"
    campos(page, f"{PREFIJO_SKU}-1", "PROBE 768 repetido", unidad=unidad)
    page.click('#productoPanel [data-accion="agregar"]')
    expect(page.locator("#producto-error-sku")).to_be_visible(timeout=10000)
    captura(page, "1366x768", "panel_error")
    campos(page, sku, "PROBE panel 768", unidad=unidad)
    page.click('#productoPanel [data-accion="agregar"]')
    expect(page.locator("#productoPanel [data-drawer-status]")).to_have_text("Producto «PROBE panel 768» guardado", timeout=10000)
    captura(page, "1366x768", "tras_agregar_otro")
    skus.append(sku)
    # Tras «agregar otro» el formulario queda limpio: Escape cierra sin preguntar.
    page.keyboard.press("Escape")
    expect(page.locator("#productoPanel")).to_be_hidden(timeout=5000)
    verificar("1366x768: escape sin datos tras «agregar otro» cierra sin confirmación", not page.locator("#app360ConfirmModal").is_visible())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--etiqueta", default=os.environ.get("E2E_ETIQUETA", "despues"))
    args = parser.parse_args()
    INFORME["etiqueta"] = args.etiqueta
    if not DB_URL or not ADMIN_PASSWORD:
        print("Faltan E2E_DATABASE_URL o E2E_ADMIN_PASSWORD.")
        return 2

    unidad = unidad_id()
    skus = []
    with sync_playwright() as p:
        navegador = p.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        contexto = navegador.new_context(viewport={"width": 1440, "height": 900}, locale="es-AR")
        page = contexto.new_page()
        page.on("console", lambda m: CONSOLA.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: ERRORES_PAGINA.append(str(e)))
        login(page)
        verificar("login del admin", "/login" not in page.url and page.locator("#password").count() == 0)
        escenario_escritorio(page, unidad, skus)
        escenario_1366(page, unidad, skus)
        navegador.close()

    api_final = None
    with sync_playwright() as p:
        navegador = p.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        page = navegador.new_context().new_page()
        login(page)
        api_final = productos_api(page) or {}
        navegador.close()
    presentes = [s for s in skus if s in api_final]
    verificar(f"cierre: los {len(skus)} productos del recorrido están en la API", len(presentes) == len(skus), f"{len(presentes)}/{len(skus)}")
    # El navegador registra como consola cada recurso fallido. Se cuentan aparte: los 422 de
    # /products/new (validaciones que el recorrido provoca a propósito) y el 404 de /favicon.ico
    # (la app no sirve favicon). Cualquier otro error de consola o de página es falla.
    recursos = [m for m in CONSOLA if m.startswith("Failed to load resource")]
    validacion = [m for m in recursos if "status of 422" in m]
    favicon = [m for m in recursos if "status of 404" in m]
    inesperados = [m for m in CONSOLA if m not in validacion and m not in favicon]
    verificar("consola: sin errores de JavaScript ni recursos inesperados", not inesperados and not ERRORES_PAGINA, inesperados or ERRORES_PAGINA)
    INFORME["consola_recursos_esperados"] = {"422_validacion": len(validacion), "404_favicon": len(favicon)}
    INFORME["productos_creados"] = skus
    fallas = [r for r in RESULTADOS if not r["ok"]]
    INFORME["resumen"] = {"total": len(RESULTADOS), "ok": len(RESULTADOS) - len(fallas), "fallas": len(fallas)}
    os.makedirs(os.path.join(CAPTURAS, args.etiqueta), exist_ok=True)
    with open(os.path.join(CAPTURAS, args.etiqueta, "informe.json"), "w", encoding="utf-8") as archivo:
        json.dump(INFORME, archivo, ensure_ascii=False, indent=2)
    print(f"RESUMEN {INFORME['resumen']}")
    return 0 if not fallas else 1


if __name__ == "__main__":
    sys.exit(main())
