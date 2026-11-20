"""Recorrido E2E del panel lateral de Ubicaciones (SIS-2B, corte 3), con Playwright en es-AR.

Qué verifica, con captura en cada pantalla tocada:
- Lista vacía: estado vacío con su botón que abre el panel; Escape sin datos cierra sin preguntar.
- «Guardar» crea la ubicación, cierra el panel, la fila nueva aparece en la lista y en la base; el foco vuelve
  al disparador y el aviso dice «Ubicación «…» guardada».
- «Guardar y agregar otro» tres veces: el panel queda abierto, el tipo se conserva, el nombre se limpia, el foco
  vuelve al nombre, y cada alta coincide con la lista y la base.
- Error por campo desde el servidor (422 con aviso en #ubicacion-error-name); requerido del navegador sin envío.
- Escape con datos pide confirmación (cancelar mantiene; aceptar cierra sin guardar); Escape sin datos cierra.
- Escapes: nombre con <b>, & y comillas se guarda y se muestra como texto en la lista.
- Página clásica /locations/new guarda con redirect a /locations; /locations/edit/<id> carga los valores.
- Pie visible y botones dentro de la ventana a 1366×768. Botones primarios (panel cerrado y abierto), contraste
  del pie y errores de consola.

Datos sintéticos rotulados PROBE-UBIC-<sufijo>. La lista debe estar vacía al empezar (la base de la instancia
propia no tiene ubicaciones). Requisitos: la app en E2E_BASE_URL con la base E2E_DATABASE_URL recién preparada;
E2E_ADMIN_PASSWORD del admin de esa base. Capturas e informe JSON en E2E_CAPTURAS/<etiqueta>/.
Código de salida 0 solo si todas las verificaciones pasan.

Uso:
    E2E_BASE_URL=http://127.0.0.1:5094 E2E_DATABASE_URL=... E2E_ADMIN_PASSWORD=... \\
        /root/.cache/app360-e2e-venv/bin/python scripts/dev_preview/e2e_ubicaciones_panel.py --etiqueta despues
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
PREFIJO = f"PROBE-UBIC-{datetime.now().strftime('%H%M%S')}"
N1 = f"{PREFIJO} nave norte"
N2 = f"{PREFIJO} sucursal centro"
N3 = f"{PREFIJO} sucursal sur"
N4 = f"{PREFIJO} <b>Dep & \"Oeste\"</b>"
N5 = f"{PREFIJO} nave 1366"
CLASICO = f"{PREFIJO} clasico"
N7 = f"{PREFIJO} <em>Norte & \"Dos\"</em>"

RESULTADOS = []
CONSOLA = []
ERRORES_PAGINA = []
INFORME = {"etiqueta": "", "base_url": BASE_URL, "verificaciones": RESULTADOS}


def verificar(nombre, ok, detalle=""):
    RESULTADOS.append({"nombre": nombre, "ok": bool(ok), "detalle": str(detalle)})
    marca = "OK   " if ok else "FALLA"
    print(f"{marca} {nombre}" + (f" [{detalle}]" if detalle and not ok else ""))


def consulta(sql, params=()):
    with psycopg2.connect(DB_URL) as conexion, conexion.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


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


def filas(page):
    """Filas de la región de la lista: [id, nombre, tipo]."""
    registros = page.locator("[data-locations-region] tr[data-location-id]")
    salida = []
    for i in range(registros.count()):
        celdas = [c.strip() for c in registros.nth(i).locator("td").all_inner_texts()]
        salida.append({"id": registros.nth(i).get_attribute("data-location-id"), "celdas": celdas})
    return salida


def esperar_fila(page, nombre, tipo, segundos=10):
    """La lista se refresca de forma asíncrona tras guardar: se sondea hasta ver la fila nueva."""
    limite = time.time() + segundos
    while time.time() < limite:
        coincidencias = [f for f in filas(page) if f["celdas"][1] == nombre and f["celdas"][2] == tipo]
        if len(coincidencias) == 1:
            return coincidencias
        page.wait_for_timeout(200)
    return [f for f in filas(page) if f["celdas"][1] == nombre and f["celdas"][2] == tipo]


def abrir_panel(page, selector='[data-drawer-open="ubicacionPanel"]'):
    page.locator(selector).first.click()
    expect(page.locator("#ubicacionPanel")).to_be_visible()


def estado(page):
    return page.locator("#ubicacionPanel [data-drawer-status]").inner_text().strip()


def fase_vacia(page):
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(BASE_URL + "/locations", wait_until="load")
    conteo = consulta("SELECT count(*) FROM locations")[0][0]
    verificar("lista vacía: la base no tiene ubicaciones al empezar", conteo == 0, conteo)
    verificar("lista vacía: estado vacío con su botón", page.locator("[data-locations-region] .empty-state").count() == 1)
    verificar(
        "lista vacía: sin botón de cabecera (SIS-1A)",
        page.locator(".panel-header .action-bar [data-drawer-open]").count() == 0,
    )
    captura(page, "1440x900", "lista_vacia")
    abrir_panel(page, '[data-drawer-open="ubicacionPanel"]:has-text("Crear primera ubicación")')
    verificar("vacía: foco en el nombre al abrir", page.evaluate("document.activeElement.id") == "ubicacion-nombre")
    captura(page, "1440x900", "panel_vacio")
    page.keyboard.press("Escape")
    expect(page.locator("#ubicacionPanel")).to_be_hidden(timeout=5000)
    verificar("vacía: Escape sin datos cierra sin confirmación", not page.locator("#app360ConfirmModal").is_visible())


def escenario_escritorio(page):
    page.goto(BASE_URL + "/locations", wait_until="load")
    abrir_panel(page, '[data-drawer-open="ubicacionPanel"]:has-text("Crear primera ubicación")')
    page.fill("#ubicacion-nombre", N1)
    page.select_option("#ubicacion-tipo", "nave")
    page.click('#ubicacionPanel [data-accion="guardar"]')
    expect(page.locator("#ubicacionPanel")).to_be_hidden(timeout=10000)
    fila = esperar_fila(page, N1, "nave")
    verificar("guardar: la fila nueva aparece en la lista con nombre y tipo", len(fila) == 1, filas(page)[:3])
    verificar(
        "guardar: el foco vuelve al disparador",
        page.evaluate("document.activeElement.dataset.drawerOpen") == "ubicacionPanel",
    )
    verificar(
        "guardar: aviso «Ubicación «…» guardada»",
        page.get_by_text(f"Ubicación «{N1}» guardada").first.is_visible(),
    )
    verificar("guardar: persistido en la base", consulta("SELECT name, type FROM locations WHERE name=%s", (N1,)) == [(N1, "nave")])
    captura(page, "1440x900", "tras_guardar")

    primarios_cerrado = page.locator(".panel-header .btn-primary:visible").count()
    verificar("lista con datos: un solo botón primario en la cabecera con el panel cerrado", primarios_cerrado == 1, primarios_cerrado)
    abrir_panel(page)
    primarios = page.locator("#ubicacionPanel .app-actions__primary:visible").count()
    verificar("panel: una sola acción primaria en el pie", primarios == 1, primarios)
    primario = page.evaluate(
        "(() => { const b = document.querySelector('#ubicacionPanel .app-actions__primary');"
        " const s = getComputedStyle(b); return [s.color, s.backgroundColor]; })()"
    )
    ratio = contraste(rgb_de(primario[0]), rgb_de(primario[1]))
    verificar("pie: contraste del botón primario >= 4,5:1", ratio >= 4.5, round(ratio, 2))
    fondo = page.evaluate("getComputedStyle(document.querySelector('#ubicacionPanel footer')).backgroundColor")
    color_sec = page.evaluate("getComputedStyle(document.querySelector('#ubicacionPanel .app-actions__secondary')).color")
    ratio_sec = contraste(rgb_de(color_sec), rgb_de(fondo))
    verificar("pie: contraste del botón secundario >= 4,5:1", ratio_sec >= 4.5, round(ratio_sec, 2))
    page.keyboard.press("Escape")
    expect(page.locator("#ubicacionPanel")).to_be_hidden(timeout=5000)

    # Guardar y agregar otro: el tipo se conserva; el nombre, no.
    altas = [(N2, "sucursal"), (N3, "sucursal"), (N4, "nave")]
    abrir_panel(page)
    for indice, (nombre, tipo) in enumerate(altas, start=1):
        page.fill("#ubicacion-nombre", nombre)
        page.select_option("#ubicacion-tipo", tipo)
        page.click('#ubicacionPanel [data-accion="agregar"]')
        expect(page.locator("#ubicacionPanel [data-drawer-status]")).to_have_text(
            f"Ubicación «{nombre}» guardada", timeout=10000
        )
        verificar(f"agregar otro {indice}: el panel sigue abierto", page.locator("#ubicacionPanel").is_visible())
        verificar(f"agregar otro {indice}: el nombre se limpia", page.input_value("#ubicacion-nombre") == "")
        verificar(
            f"agregar otro {indice}: el tipo se conserva ({tipo})",
            page.input_value("#ubicacion-tipo") == tipo,
        )
        verificar(
            f"agregar otro {indice}: foco en el nombre",
            page.evaluate("document.activeElement.id") == "ubicacion-nombre",
        )
        fila = esperar_fila(page, nombre, tipo)
        verificar(f"agregar otro {indice}: la lista muestra «{nombre}» con tipo {tipo}", len(fila) == 1, fila)
        verificar(
            f"agregar otro {indice}: la base coincide",
            consulta("SELECT type FROM locations WHERE name=%s", (nombre,)) == [(tipo,)],
        )
        if indice == 1:
            captura(page, "1440x900", "tras_agregar_otro")

    # Error por campo que devuelve el servidor (422). El navegador no envía un campo sin name: se simula
    # un cliente que no lo manda, quitando el atributo; el servidor responde con su aviso por campo.
    page.fill("#ubicacion-nombre", f"{PREFIJO} sin campo")
    page.evaluate("document.getElementById('ubicacion-nombre').removeAttribute('name')")
    page.click('#ubicacionPanel [data-accion="agregar"]')
    expect(page.locator("#ubicacion-error-name")).to_be_visible(timeout=10000)
    verificar(
        "error por campo: aviso junto al nombre desde el servidor",
        page.inner_text("#ubicacion-error-name") == "Ingresá el nombre de la ubicación.",
    )
    page.evaluate("document.getElementById('ubicacion-nombre').setAttribute('name', 'name')")
    verificar("error por campo: no guardó", consulta("SELECT count(*) FROM locations WHERE name LIKE %s", (f"{PREFIJO} sin campo%",))[0][0] == 0)
    captura(page, "1440x900", "panel_error")

    # Requerido del navegador: sin nombre no hay envío.
    page.fill("#ubicacion-nombre", "")
    page.click('#ubicacionPanel [data-accion="guardar"]')
    verificar(
        "requerido del navegador: el nombre vacío no se envía",
        page.evaluate("document.getElementById('ubicacion-nombre').validity.valueMissing") is True
        and page.locator("#ubicacionPanel").is_visible(),
    )

    # Escape con datos: pide confirmación; cancelar mantiene; aceptar cierra sin guardar.
    page.fill("#ubicacion-nombre", f"{PREFIJO} borrador")
    page.keyboard.press("Escape")
    expect(page.locator("#app360ConfirmModal")).to_be_visible(timeout=5000)
    page.wait_for_timeout(600)
    page.click("#app360ConfirmCancel")
    expect(page.locator("#app360ConfirmModal")).to_be_hidden(timeout=5000)
    page.wait_for_timeout(600)
    verificar("escape con datos: cancelar mantiene el panel abierto", page.locator("#ubicacionPanel").is_visible())
    page.keyboard.press("Escape")
    expect(page.locator("#app360ConfirmModal")).to_be_visible(timeout=5000)
    page.wait_for_timeout(600)
    page.click("#app360ConfirmAccept")
    expect(page.locator("#ubicacionPanel")).to_be_hidden(timeout=5000)
    verificar(
        "escape con datos: confirmar cierra y devuelve el foco",
        page.evaluate("document.activeElement.dataset.drawerOpen") == "ubicacionPanel",
    )
    verificar("escape con datos: el borrador no se guardó", consulta("SELECT count(*) FROM locations WHERE name LIKE %s", (f"{PREFIJO} borrador%",))[0][0] == 0)

    # Escape sin datos: cierra sin preguntar.
    abrir_panel(page)
    page.keyboard.press("Escape")
    expect(page.locator("#ubicacionPanel")).to_be_hidden(timeout=5000)
    verificar("escape sin datos: cierra sin confirmación", not page.locator("#app360ConfirmModal").is_visible())

    # Escapes: el nombre con <b>, & y comillas se guarda y se ve como texto.
    abrir_panel(page)
    page.fill("#ubicacion-nombre", N7)
    page.select_option("#ubicacion-tipo", "nave")
    page.click('#ubicacionPanel [data-accion="guardar"]')
    expect(page.locator("#ubicacionPanel")).to_be_hidden(timeout=10000)
    fila = esperar_fila(page, N7, "nave")
    verificar("escapes: el nombre aparece como texto literal en la lista", len(fila) == 1, [f["celdas"][:2] for f in filas(page)][:6])
    verificar("escapes: no se genera un <b> en la lista", page.locator("[data-locations-region] b").count() == 0)
    verificar("escapes: la base guarda el texto tal cual", consulta("SELECT count(*) FROM locations WHERE name=%s", (N7,))[0][0] == 1)

    # Página clásica /locations/new: sigue guardando con redirect a la lista.
    page.goto(BASE_URL + "/locations/new", wait_until="load")
    page.fill("#ubicacion-nombre", CLASICO)
    page.select_option("#ubicacion-tipo", "sucursal")
    page.click("form:has(#ubicacion-nombre) button[type=submit]")
    page.wait_for_url(re.compile(r".*/locations/?$"), timeout=10000)
    verificar("página clásica: redirige a /locations tras guardar", page.url.rstrip("/").endswith("/locations"))
    verificar("página clásica: persistido", consulta("SELECT type FROM locations WHERE name=%s", (CLASICO,)) == [("sucursal",)])

    # Edición clásica: carga los valores guardados.
    id_n1 = consulta("SELECT id FROM locations WHERE name=%s", (N1,))[0][0]
    page.goto(BASE_URL + f"/locations/edit/{id_n1}", wait_until="load")
    verificar("edición clásica: carga el nombre", page.input_value("#ubicacion-nombre") == N1)
    verificar("edición clásica: carga el tipo", page.input_value("#ubicacion-tipo") == "nave")
    captura(page, "1440x900", "edicion_clasica")


def escenario_1366(page):
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(BASE_URL + "/locations", wait_until="load")
    captura(page, "1366x768", "lista")
    abrir_panel(page)
    captura(page, "1366x768", "panel_vacio")
    pie = page.evaluate(
        "(() => { const f = document.querySelector('#ubicacionPanel footer').getBoundingClientRect();"
        " const botones = [...document.querySelectorAll('#ubicacionPanel [data-drawer-pie] button')]"
        ".map(b => b.getBoundingClientRect()); return {bottom: f.bottom, botones: botones.map(r => [r.top, r.bottom])}; })()"
    )
    dentro = pie["bottom"] <= 768 and all(0 <= r[0] and r[1] <= 768 for r in pie["botones"])
    verificar("1366x768: pie y botones dentro de la ventana", dentro, pie)
    page.fill("#ubicacion-nombre", N5)
    page.select_option("#ubicacion-tipo", "nave")
    page.click('#ubicacionPanel [data-accion="guardar"]')
    expect(page.locator("#ubicacionPanel")).to_be_hidden(timeout=10000)
    verificar("1366x768: guardar cierra el panel", True)
    captura(page, "1366x768", "tras_guardar")


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
        fase_vacia(page)
        escenario_escritorio(page)
        escenario_1366(page)
        total = consulta("SELECT count(*) FROM locations WHERE name LIKE %s", (f"{PREFIJO}%",))[0][0]
        verificar("altas exitosas del recorrido: 7 ubicaciones en la base", total == 7, total)
        navegador.close()

    recursos = [m for m in CONSOLA if m.startswith("Failed to load resource")]
    validacion = [m for m in recursos if "status of 422" in m]
    favicon = [m for m in recursos if "status of 404" in m]
    inesperados = [m for m in CONSOLA if m not in validacion and m not in favicon]
    verificar("consola: sin errores de JavaScript ni recursos inesperados", not inesperados and not ERRORES_PAGINA, inesperados or ERRORES_PAGINA)
    INFORME["consola_recursos_esperados"] = {"422_validacion": len(validacion), "404_favicon": len(favicon)}
    fallas = [r for r in RESULTADOS if not r["ok"]]
    INFORME["resumen"] = {"total": len(RESULTADOS), "ok": len(RESULTADOS) - len(fallas), "fallas": len(fallas)}
    os.makedirs(os.path.join(CAPTURAS, args.etiqueta), exist_ok=True)
    with open(os.path.join(CAPTURAS, args.etiqueta, "informe_ubicaciones.json"), "w", encoding="utf-8") as archivo:
        json.dump(INFORME, archivo, ensure_ascii=False, indent=2)
    print(f"RESUMEN {INFORME['resumen']}")
    return 0 if not fallas else 1


if __name__ == "__main__":
    sys.exit(main())
